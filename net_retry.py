"""Retries avec backoff exponentiel et messages d'erreur clairs pour les appels reseau du pipeline
(Ollama, Pexels, Azure Speech, YouTube...).

Le workflow GitHub Actions relance deja TOUT le pipeline jusqu'a 3 fois en cas d'echec, mais une
simple coupure reseau de 2 secondes sur un telechargement Pexels ne doit pas couter la regeneration
complete du script et de la voix off : on reessaie donc au plus pres de l'appel qui a echoue.
"""
import http.client
import os
import socket
import time
import urllib.error
import urllib.request

# Codes HTTP qui valent la peine d'etre reessayes : limite de debit (429) et pannes serveur (5xx).
# Les 4xx restants (401 cle invalide, 404...) ne se corrigeront pas en reessayant.
RETRYABLE_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504}


class MissingSecretError(RuntimeError):
    """Variable d'environnement / secret absent : erreur de configuration, jamais reessayee."""


def require_env(name: str, hint: str) -> str:
    """Lit une variable d'environnement obligatoire, avec un message expliquant comment la definir
    (au lieu d'un KeyError brut illisible dans les logs GitHub Actions)."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingSecretError(
            f"{name} manquante ou vide. {hint} "
            f"(en local : setx {name} \"valeur\" ; sur GitHub Actions : Settings > Secrets and variables > Actions)."
        )
    return value


def is_transient(exc: BaseException) -> bool:
    """True si l'erreur est probablement passagere (reseau, timeout, 429/5xx)."""
    if isinstance(exc, MissingSecretError):
        return False
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in RETRYABLE_HTTP_CODES
    if isinstance(exc, urllib.error.URLError):
        return True  # DNS, connexion refusee, timeout pendant la connexion...
    return isinstance(exc, (TimeoutError, socket.timeout, ConnectionError, http.client.HTTPException))


def describe_error(exc: BaseException) -> str:
    """Resume lisible d'une erreur reseau, sans jamais inclure d'en-tetes (donc aucune cle API)."""
    if isinstance(exc, urllib.error.HTTPError):
        hints = {
            401: "cle API invalide ou expiree",
            403: "acces refuse (cle API ou quota)",
            404: "ressource introuvable",
            429: "limite de requetes atteinte",
        }
        hint = hints.get(exc.code) or ("erreur serveur" if exc.code >= 500 else "")
        return f"HTTP {exc.code}" + (f" ({hint})" if hint else "")
    if isinstance(exc, urllib.error.URLError):
        return f"reseau injoignable ({exc.reason})"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "delai depasse (timeout)"
    return f"{type(exc).__name__}: {exc}"


def _retry_after_seconds(exc: BaseException) -> float | None:
    if isinstance(exc, urllib.error.HTTPError) and exc.headers is not None:
        value = exc.headers.get("Retry-After")
        if value and value.strip().isdigit():
            return float(value.strip())
    return None


def with_retry(fn, *, what: str, attempts: int = 3, base_delay: float = 2.0, max_delay: float = 60.0,
               retry_on=is_transient, sleep=None):
    """Appelle fn() jusqu'a `attempts` fois tant que l'erreur est passagere (retry_on), avec un
    backoff exponentiel (2s, 4s, 8s... plafonne a max_delay, ou le Retry-After du serveur).
    Une erreur non passagere (cle invalide, secret manquant...) remonte immediatement."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            if attempt >= attempts or not retry_on(exc):
                raise
            delay = _retry_after_seconds(exc) or base_delay * (2 ** (attempt - 1))
            delay = min(delay, max_delay)
            print(f"    [retry] {what} : {describe_error(exc)} - nouvel essai {attempt + 1}/{attempts} dans {delay:.0f}s")
            (sleep or time.sleep)(delay)


def download_file(url: str, dest_path: str, *, timeout: float = 60, attempts: int = 3,
                  headers: dict | None = None, what: str = "telechargement") -> str:
    """Telecharge url -> dest_path avec retries. Ecrit d'abord dans un fichier .part puis renomme :
    un telechargement coupe en plein milieu ne laisse jamais un mp4/jpg tronque a l'emplacement final."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", **(headers or {})})
    tmp_path = f"{dest_path}.part"

    def _once():
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp_path, "wb") as out_f:
            out_f.write(resp.read())
        os.replace(tmp_path, dest_path)
        return dest_path

    try:
        return with_retry(_once, what=what, attempts=attempts)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
