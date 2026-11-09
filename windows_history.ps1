#requires -Version 5.1
# Read-only WinRT bridge. Private payload travels only through the parent's pipe.
param([ValidateSet('Inspect','Read')][string]$Mode='Inspect',[string]$ExcludedApps='',[string]$SensitiveTitlePattern='')
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null=[Windows.ApplicationModel.DataTransfer.Clipboard,Windows.ApplicationModel.DataTransfer,ContentType=WindowsRuntime]
    $null=[Windows.ApplicationModel.DataTransfer.ClipboardHistoryItemsResult,Windows.ApplicationModel.DataTransfer,ContentType=WindowsRuntime]
    $asTask=([System.WindowsRuntimeSystemExtensions].GetMethods()|Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    })[0]
    function Await($Operation,[Type]$ResultType) {
        $task=$asTask.MakeGenericMethod($ResultType).Invoke($null,@($Operation))
        if(-not $task.Wait(1500)){throw 'WinRT timeout'}
        $task.GetAwaiter().GetResult()
    }
    $result=Await ([Windows.ApplicationModel.DataTransfer.Clipboard]::GetHistoryItemsAsync()) ([Windows.ApplicationModel.DataTransfer.ClipboardHistoryItemsResult])
    $items=@($result.Items)
    $rows=[Collections.Generic.List[object]]::new()
    $skipped=[ordered]@{protected=0;non_text=0;oversize=0;unavailable=0;deadline=0}
    $deadline=[DateTime]::UtcNow.AddSeconds(5)
    $usedBytes=0
    if($Mode -eq 'Read' -and [string]$result.Status -eq 'Success') {
        foreach($item in ($items|Select-Object -First 25)) {
            if([DateTime]::UtcNow -gt $deadline){$skipped.deadline++;continue}
            $formats=@($item.Content.AvailableFormats)
            # History cannot reconstruct the original foreground process. Do not
            # reinterpret a protection marker as an invitation to read its body.
            if($formats -contains 'ExcludeClipboardContentFromMonitorProcessing' -or
               $formats -contains 'CanIncludeInClipboardHistory'){$skipped.protected++;continue}
            if($formats -notcontains 'Text'){$skipped.non_text++;continue}
            $app=[string]$item.Content.Properties.ApplicationName
            $title=[string]$item.Content.Properties.Title
            $excludedNames=@($ExcludedApps -split ',')
            if($app -and (@($excludedNames|Where-Object {$_ -and ($app -ieq $_ -or $app -ieq ($_ -replace '\.exe$',''))}).Count)){$skipped.protected++;continue}
            if($SensitiveTitlePattern -and $title -match $SensitiveTitlePattern){$skipped.protected++;continue}
            try {
                $text=Await ($item.Content.GetTextAsync()) ([string])
                $bytes=[Text.Encoding]::UTF8.GetByteCount($text)
                if($text.Length -gt 100000 -or $usedBytes+$bytes -gt 1800000){$skipped.oversize++;continue}
                $rows.Add([ordered]@{id=[string]$item.Id;captured_at=$item.Timestamp.ToUniversalTime().ToString('o');text=$text;source_app=$app;protected=$false})
                $usedBytes+=$bytes
            } catch {$skipped.unavailable++}
        }
    }
    [ordered]@{schema='starlight.windows-history.v1';status=[string]$result.Status;
        history_enabled=[Windows.ApplicationModel.DataTransfer.Clipboard]::IsHistoryEnabled();
        roaming_enabled=[Windows.ApplicationModel.DataTransfer.Clipboard]::IsRoamingEnabled();
        available=$items.Count;records=@($rows.ToArray());skipped=$skipped} | ConvertTo-Json -Depth 5 -Compress
} catch {
    # Exception details can contain values supplied by a source application.
    [ordered]@{schema='starlight.windows-history.v1';status='Unavailable';history_enabled=$false;
        roaming_enabled=$false;available=0;records=@();skipped=@{unavailable=1}}|ConvertTo-Json -Depth 4 -Compress
    exit 1
}
