<#
Wrapper de robustesse pour les taches planifiees YouTubeAI-*.

Probleme resolu : quand le PC est eteint/en veille au moment d'un horaire planifie,
Windows rattrape les runs manques au demarrage. Si plusieurs runs manques se
rattrapent en meme temps (ex: PC reste eteint plusieurs jours, ou juste plusieurs
heures), ils se lancent en parallele et se font concurrence (CPU/GPU/ffmpeg), ce
qui peut faire planter l'un d'eux - et meme serialises, publier 8 videos d'affilee
en quelques dizaines de minutes ferait un pic de publication anormal sur la chaine.

Ce script :
  1. Attend un delai propre a son horaire prevu (-ScheduledHour) : au demarrage du
     PC, Windows declenche tous les rattrapages manques quasi simultanement, dans
     un ordre non garanti. Ce delai (quelques secondes par heure de la journee)
     fait que la tache normalement prevue le plus tot dans la journee est aussi
     celle qui reclame un creneau d'etalement en premier (etape 2), donc les
     rattrapages sont traites dans le meme ordre que l'horaire prevu au lieu d'un
     ordre arbitraire.
  2. Reclame un "creneau" dans un fichier partage (logs\next_slot.txt, protege par
     un Mutex dedie) espace d'au moins -SpreadMinutes par rapport au creneau
     precedemment reclame, puis attend ce creneau avant de continuer. Resultat :
     si plusieurs runs se rattrapent en meme temps, ils sont etales dans la
     journee au lieu de se suivre en rafale. En fonctionnement normal (pas de
     rattrapage), le creneau precedent est deja dans le passe, donc ca n'ajoute
     aucune attente.
  3. Prend un verrou global d'execution (Mutex nomme) avant de lancer le pipeline,
     pour que les differents runs (video longue + shorts) s'executent toujours
     l'un apres l'autre, jamais en parallele.
  4. Reessaie automatiquement (par defaut 2 fois) si le run echoue (code de sortie
     non nul), avec une pause entre les tentatives.
  5. Journalise ses propres messages dans le meme fichier de log que le pipeline.
#>
param(
    [Parameter(Mandatory = $true)][string]$Script,
    [string]$ExtraArgs = "--publish",
    [Parameter(Mandatory = $true)][string]$LogFile,
    [int]$MaxRetries = 2,
    [int]$RetryDelaySeconds = 120,
    [int]$LockTimeoutMinutes = 180,
    [int]$ScheduledHour = -1,
    [int]$SpreadMinutes = 40
)

$ProjectDir = "C:\Users\ovila\youtube-ai-generator"
Set-Location $ProjectDir
$LogPath = Join-Path $ProjectDir $LogFile
New-Item -ItemType Directory -Force -Path (Split-Path $LogPath) | Out-Null

function Write-Log([string]$msg) {
    # Add-Content peut echouer ("Le flux ne peut pas etre lu") si un autre run
    # (ex: plusieurs taches Shorts qui se rattrapent en meme temps au demarrage,
    # avant meme d'avoir demande le Mutex) ecrit dans le meme fichier de log au
    # meme instant. On ouvre donc le fichier nous-memes en FileShare.ReadWrite
    # et on reessaie en cas de contention passagere.
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [safe-wrapper] $msg"
    for ($i = 0; $i -lt 10; $i++) {
        try {
            $stream = [System.IO.File]::Open($LogPath, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
            try {
                $writer = New-Object System.IO.StreamWriter($stream, [System.Text.Encoding]::Default)
                $writer.WriteLine($line)
                $writer.Flush()
            }
            finally {
                $writer.Dispose()
                $stream.Dispose()
            }
            return
        }
        catch {
            Start-Sleep -Milliseconds (Get-Random -Minimum 100 -Maximum 400)
        }
    }
}

if ($ScheduledHour -ge 0) {
    $staggerSeconds = $ScheduledHour * 5
    Write-Log "Delai d'ordonnancement (horaire prevu ${ScheduledHour}h) : ${staggerSeconds}s avant de reclamer un creneau d'etalement."
    Start-Sleep -Seconds $staggerSeconds
}

function Get-CatchupSlot([int]$spreadMinutes) {
    # Fichier partage entre toutes les taches YouTubeAI-* pour etaler les
    # rattrapages groupes. Protege par un Mutex dedie (distinct du Mutex
    # d'execution) car on doit pouvoir reclamer un creneau meme pendant qu'un
    # autre run est deja en train de tourner.
    $slotFile = Join-Path $ProjectDir "logs\next_slot.txt"
    $slotMutex = New-Object System.Threading.Mutex($false, "Global\YouTubeAI-SlotLock")
    $acq = $false
    try {
        try {
            $acq = $slotMutex.WaitOne([TimeSpan]::FromSeconds(30))
        }
        catch [System.Threading.AbandonedMutexException] {
            $acq = $true
        }
        if (-not $acq) {
            return (Get-Date)
        }

        $now = Get-Date
        $nextSlot = $now
        if (Test-Path $slotFile) {
            $raw = Get-Content -Path $slotFile -Raw -ErrorAction SilentlyContinue
            $parsed = [DateTime]::MinValue
            if ($raw -and [DateTime]::TryParse($raw.Trim(), [ref]$parsed) -and $parsed -gt $now) {
                $nextSlot = $parsed
            }
        }
        Set-Content -Path $slotFile -Value $nextSlot.AddMinutes($spreadMinutes).ToString("o") -Encoding ascii
        return $nextSlot
    }
    finally {
        if ($acq) { $slotMutex.ReleaseMutex() }
        $slotMutex.Dispose()
    }
}

$mySlot = Get-CatchupSlot -spreadMinutes $SpreadMinutes
$waitSeconds = [Math]::Round(($mySlot - (Get-Date)).TotalSeconds)
if ($waitSeconds -gt 1) {
    Write-Log "Etalement des rattrapages : creneau attribue a $($mySlot.ToString('HH:mm:ss')), attente de ${waitSeconds}s avant de demander le verrou."
    Start-Sleep -Seconds $waitSeconds
}

$mutex = New-Object System.Threading.Mutex($false, "Global\YouTubeAI-PipelineLock")
$acquired = $false
try {
    try {
        $acquired = $mutex.WaitOne([TimeSpan]::FromMinutes($LockTimeoutMinutes))
    }
    catch [System.Threading.AbandonedMutexException] {
        Write-Log "Verrou abandonne detecte (le run precedent a probablement plante sans le liberer) - on le recupere."
        $acquired = $true
    }

    if (-not $acquired) {
        Write-Log "ERREUR: verrou toujours pris par un autre run apres $LockTimeoutMinutes min. Abandon de ce lancement ($Script)."
        exit 1
    }

    Write-Log "Verrou obtenu. Lancement: python $Script $ExtraArgs"

    $attempt = 0
    $success = $false
    while (-not $success -and $attempt -le $MaxRetries) {
        $attempt++
        if ($attempt -gt 1) {
            Write-Log "Tentative $attempt / $($MaxRetries + 1) apres echec precedent (pause ${RetryDelaySeconds}s)..."
            Start-Sleep -Seconds $RetryDelaySeconds
        }

        # Redirection via cmd.exe (et non l'operateur PowerShell *>>) pour garder le meme
        # encodage (ANSI) que le reste du fichier de log - *>> ecrit en UTF-16 et corrompt
        # l'affichage du log existant.
        $cmdLine = "python `"$Script`" $ExtraArgs >> `"$LogPath`" 2>&1"
        & cmd /c $cmdLine
        $exitCode = $LASTEXITCODE

        if ($exitCode -eq 0) {
            $success = $true
            Write-Log "OK (tentative $attempt)."
        }
        else {
            Write-Log "ECHEC (code $exitCode) a la tentative $attempt."
        }
    }

    if (-not $success) {
        Write-Log "ABANDON definitif apres $($MaxRetries + 1) tentatives pour $Script."
        exit 1
    }
}
finally {
    if ($acquired) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
