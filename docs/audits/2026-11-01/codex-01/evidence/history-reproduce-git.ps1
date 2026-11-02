$ErrorActionPreference = 'Stop'
$auditRepo = 'C:\Users\auditor\Documents\Codex\2026-11-01\files-pasted-by-the-user-you\work\brand-me-labs-audit'
$auditOut = 'C:\Users\auditor\Documents\Codex\2026-11-01\files-pasted-by-the-user-you\outputs\brand-me-labs-audit-2026-11-01-codex-01\evidence'
$auditBase = 'ed19dc151d103b108cf972e6d37971c55d5dcf60'
Set-Location -LiteralPath $auditRepo
$auditItems = @()
$auditIndex = 0
$auditRefs = git for-each-ref '--format=%(refname)|%(objectname)|%(committerdate:iso-strict)|%(subject)' refs/remotes/origin
foreach ($auditRef in $auditRefs) {
  $auditParts = $auditRef -split '\|',4
  if ($auditParts[0] -eq 'refs/remotes/origin/HEAD') { continue }
  $auditIndex++
  $auditSha = $auditParts[1]
  $auditMergeBase = git merge-base $auditBase $auditSha
  $auditCounts = (git rev-list --left-right --count "$auditBase...$auditSha") -split '\s+'
  $auditCommits = @(git log '--format=%H|%cs|%s' "$auditBase..$auditSha")
  $auditCherry = @(git cherry -v $auditBase $auditSha)
  $auditChanged = @(git diff --name-status "$auditMergeBase..$auditSha")
  $auditCurrentDiff = @(git diff --name-status "$auditBase..$auditSha")
  $auditItem = [ordered]@{
    id = ('BR-{0:D3}' -f $auditIndex); exact_ref = $auditParts[0]; tip_sha = $auditSha
    last_activity = $auditParts[2]; tip_subject = $auditParts[3]; comparison_ref='refs/remotes/origin/main'
    comparison_sha=$auditBase; merge_base=$auditMergeBase; ahead=[int]$auditCounts[1]; behind=[int]$auditCounts[0]
    tree_sha=(git rev-parse "$auditSha^{tree}"); unique_commits=$auditCommits; patch_equivalence=$auditCherry
    branch_changes_from_merge_base=$auditChanged; current_tree_difference_from_main=$auditCurrentDiff
    recommendation='UNKNOWN'; confidence='pending semantic/consumer review'; reviewed='metadata, ancestry, patch equivalence, changed-file inventory'
  }
  $auditItems += [pscustomobject]$auditItem
}
$auditItems | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $auditOut 'history-git-branches-raw.json') -Encoding utf8
git log --all '--format=%H|%P|%cs|%s' | Set-Content -LiteralPath (Join-Path $auditOut 'history-all-commits.txt') -Encoding utf8
git log --all --grep='revert' -i '--format=%H|%P|%cs|%s' | Set-Content -LiteralPath (Join-Path $auditOut 'history-revert-commits.txt') -Encoding utf8
git worktree list --porcelain | Set-Content -LiteralPath (Join-Path $auditOut 'history-clone-worktrees.txt') -Encoding utf8
git tag --format='%(refname)|%(objectname)|%(creatordate:iso-strict)' | Set-Content -LiteralPath (Join-Path $auditOut 'history-tags.txt') -Encoding utf8
$auditItems | Select-Object id,exact_ref,ahead,behind,tip_subject | Format-Table -AutoSize | Out-String -Width 260 | Write-Output
