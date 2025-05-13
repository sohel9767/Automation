# Automation

# Connect to Microsoft Graph
Connect-MgGraph -Scopes "Application.Read.All", "Directory.Read.All"

# Collect expiring secrets
$expiringSecrets = @()
$applications = Get-MgApplication -All

foreach ($app in $applications) {
    foreach ($secret in $app.PasswordCredentials) {
        $daysLeft = ($secret.EndDateTime - (Get-Date)).Days

        if ($daysLeft -le 30) {
            $owners = Get-MgApplicationOwner -ApplicationId $app.Id | Select-Object -ExpandProperty UserPrincipalName
            if (-not $owners) {
                $owners = @("your.name@domain.com")  # fallback email
            }

            $expiringSecrets += [PSCustomObject]@{
                AppName     = $app.DisplayName
                AppId       = $app.AppId
                ExpiryDate  = $secret.EndDateTime
                DaysLeft    = $daysLeft
                Owners      = ($owners -join ", ")
            }
        }
    }
}

# Build HTML email table
$html = "<style>table{border-collapse:collapse;}td,th{border:1px solid black;padding:5px;}</style>"
$html += "<h2>Secrets Expiring in Next 30 Days</h2><table><tr><th>App Name</th><th>App ID</th><th>Expiry Date</th><th>Days Left</th><th>Owners</th></tr>"

foreach ($entry in $expiringSecrets) {
    $html += "<tr><td>$($entry.AppName)</td><td>$($entry.AppId)</td><td>$($entry.ExpiryDate)</td><td>$($entry.DaysLeft)</td><td>$($entry.Owners)</td></tr>"
}
$html += "</table>"

# Send Email
Send-MailMessage -To "group@domain.com" -From "automation@domain.com" `
    -Subject "App Registration Secrets Expiring Soon" `
    -BodyAsHtml $html -SmtpServer "smtp.domain.com"
