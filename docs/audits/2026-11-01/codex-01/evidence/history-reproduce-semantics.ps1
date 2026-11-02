$ErrorActionPreference = 'Stop'
$auditRepo = 'C:\Users\auditor\Documents\Codex\2026-11-01\files-pasted-by-the-user-you\work\brand-me-labs-audit'
$auditOut = 'C:\Users\auditor\Documents\Codex\2026-11-01\files-pasted-by-the-user-you\outputs\brand-me-labs-audit-2026-11-01-codex-01\evidence'
Set-Location -LiteralPath $auditRepo
$auditBranches = Get-Content -LiteralPath (Join-Path $auditOut 'history-git-branches-raw.json') -Raw | ConvertFrom-Json
$auditPrs = Get-Content -LiteralPath (Join-Path $auditOut 'history-github-prs.json') -Raw | ConvertFrom-Json
$auditResult = @()
foreach ($auditBranch in $auditBranches) {
 $auditName = $auditBranch.exact_ref -replace '^refs/remotes/origin/',''
 $auditRelated = @($auditPrs | Where-Object head_ref -eq $auditName)
 $auditMerged = @($auditRelated | Where-Object { $_.merged_at -and $_.base_ref -eq 'main' })
 $auditMergeComparisons = @()
 foreach ($auditPr in $auditMerged) {
  git cat-file -e "$($auditPr.merge_commit_sha)^{commit}" 2>$null
  if ($LASTEXITCODE -ne 0) { continue }
  $auditMergeParent = git rev-parse "$($auditPr.merge_commit_sha)^1"
  $auditDiffPatch = @(git diff $auditBranch.merge_base $auditBranch.tip_sha | git patch-id --stable)
  $auditMergePatch = @(git diff $auditMergeParent $auditPr.merge_commit_sha | git patch-id --stable)
  $auditSameTree = (git rev-parse "$($auditPr.merge_commit_sha)^{tree}") -eq $auditBranch.tree_sha
  $auditMergeComparisons += [pscustomobject]@{pr=$auditPr.number; merge_sha=$auditPr.merge_commit_sha; branch_aggregate_patch=$auditDiffPatch; merge_patch=$auditMergePatch; identical_tree_at_merge=$auditSameTree; aggregate_equivalent=($auditDiffPatch.Count -gt 0 -and $auditMergePatch.Count -gt 0 -and (($auditDiffPatch[0] -split ' ')[0] -eq ($auditMergePatch[0] -split ' ')[0]))}
 }
 $auditNewPaths=@()
 foreach ($auditChange in $auditBranch.branch_changes_from_merge_base) {
  $auditFields=$auditChange -split "`t"
  if ($auditFields[0] -ne 'A') { continue }
  $auditPath=$auditFields[-1]
  $auditMainBlob = git ls-tree origin/main -- $auditPath
  $auditTipBlob = git ls-tree $auditBranch.tip_sha -- $auditPath
  $auditNewPaths += [pscustomobject]@{path=$auditPath; present_on_main=[bool]$auditMainBlob; identical_blob=($auditMainBlob -eq $auditTipBlob)}
 }
 $auditResult += [pscustomobject]@{id=$auditBranch.id; ref=$auditName; prs=$auditRelated; squash_comparisons=$auditMergeComparisons; added_paths_current_main=$auditNewPaths}
}
$auditResult | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $auditOut 'history-semantic-comparisons.json') -Encoding utf8
$auditResult | Where-Object { $_.squash_comparisons.Count -gt 0 } | ForEach-Object { $_.id; $_.squash_comparisons | Format-Table pr,merge_sha,identical_tree_at_merge,aggregate_equivalent -AutoSize | Out-String }
