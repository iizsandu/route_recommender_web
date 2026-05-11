# Usage: .\scripts\deploy.ps1 -Sha <git-sha>
# If -Sha is omitted, deploys the latest image tag.
#
# WHY this script exists: student Azure account cannot create app registrations,
# so GitHub Actions cannot authenticate to Azure. CI builds and pushes the image;
# this script does the final "point Container App at new image" step from a local
# terminal where az login already works.

param(
    [string]$Sha = "latest"
)

$IMAGE = "ghcr.io/iizsandu/route-recommender-backend:$Sha"
$APP   = "route-recommender-backend"
$RG    = "route-recommender-rg"

Write-Host "Deploying $IMAGE to $APP ..."

az containerapp update `
    --name $APP `
    --resource-group $RG `
    --image $IMAGE

if ($LASTEXITCODE -eq 0) {
    $fqdn = az containerapp show --name $APP --resource-group $RG --query "properties.configuration.ingress.fqdn" -o tsv
    Write-Host ""
    Write-Host "Deployed. Verifying health..."
    Start-Sleep -Seconds 5
    curl -s "https://$fqdn/health"
} else {
    Write-Host "Deploy failed. Check 'az containerapp logs show --name $APP --resource-group $RG --follow'"
}
