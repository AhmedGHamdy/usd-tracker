# Removes the USD-EGP scheduled tasks. Leaves your code / .env / logs alone.
$ErrorActionPreference = "Continue"

Write-Host "Removing USD-EGP scheduled tasks..." -ForegroundColor Yellow

foreach ($name in @("USD-EGP-Tracker", "USD-EGP-Daily")) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "  Removed: $name" -ForegroundColor Green
    } else {
        Write-Host "  Not found: $name (skipped)" -ForegroundColor Gray
    }
}

Write-Host "`nDone. Your code, .env, state.json, and logs are untouched." -ForegroundColor Cyan
Write-Host "To disable at the GitHub Actions side too, visit:"
Write-Host "  https://github.com/AhmedGHamdy/usd-tracker/settings/actions  -> Disable Actions"
