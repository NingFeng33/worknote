# WorkNote - PowerShell integration.  Loaded from your $PROFILE by install.ps1:
#   . "$HOME\bin\worknote\note.ps1"

$global:WorkNotePy = Join-Path $PSScriptRoot 'note.py'
if (Get-Command py -ErrorAction SilentlyContinue) {
    $global:WorkNotePython = @('py', '-3')
} else {
    $global:WorkNotePython = @('python')
}
$global:WorkNoteRaw = $null

function global:note {
    $exe = $global:WorkNotePython[0]
    $pre = @($global:WorkNotePython | Select-Object -Skip 1)
    if ($null -ne $global:WorkNoteRaw) {
        # text captured by the Enter hook: hand it over untouched
        $env:WORKNOTE_RAW = $global:WorkNoteRaw
        $global:WorkNoteRaw = $null
        try { & $exe @pre $global:WorkNotePy }
        finally { Remove-Item Env:WORKNOTE_RAW -ErrorAction SilentlyContinue }
    } else {
        & $exe @pre $global:WorkNotePy @args
    }
}

# PowerShell would treat  #  as a comment and  > | ; &  as operators, cutting your note.
# This Enter-key hook keeps everything typed after "note " for the tool, and turns it
# into a comment for PowerShell (shown as "note # ...") so nothing in it is executed.
if (Get-Module PSReadLine) {
    Set-PSReadLineKeyHandler -Key Enter -BriefDescription 'WorkNoteAcceptLine' -ScriptBlock {
        $line = $null; $cursor = $null
        try {
            [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState([ref]$line, [ref]$cursor)
            if ($line -match '^\s*note\s+((?:-n\s+\S+\s+)?(?:-p\s+)?[^\s#-].*)$' -and
                $line -notmatch '^\s*note\s+(table|pic)(\s|$)') {
                $global:WorkNoteRaw = $Matches[1]
                [Microsoft.PowerShell.PSConsoleReadLine]::AddToHistory($line)
                [Microsoft.PowerShell.PSConsoleReadLine]::Replace(0, $line.Length, "note # $($Matches[1])")
            }
        } catch { }
        [Microsoft.PowerShell.PSConsoleReadLine]::AcceptLine()
    }

    if (-not $global:WorkNoteHistoryHooked) {
        $global:WorkNoteHistoryHooked = $true
        $global:WorkNotePrevHistoryHandler = (Get-PSReadLineOption).AddToHistoryHandler
        Set-PSReadLineOption -AddToHistoryHandler {
            param([string]$l)
            if ($l -like 'note # *' -or $l -like 'note --b64 *') { return $false }
            if ($global:WorkNotePrevHistoryHandler -is [System.Func[string, object]]) {
                return $global:WorkNotePrevHistoryHandler.Invoke($l)
            }
            return $true
        }
    }
}
