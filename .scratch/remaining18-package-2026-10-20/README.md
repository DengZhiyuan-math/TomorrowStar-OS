# Remaining engineering package verification

```json
{
  "source_candidate_frozen": true,
  "full_manifest_scope_bound": true,
  "only_latest_two_fixes_scope_claimed": false,
  "build_completed": true,
  "bundle_signature_verified": true,
  "bundled_backend_verification_passed": true,
  "isolated_synthetic_chrome_pdf_export_passed": true,
  "source_equality_after_build_passed": true,
  "source_equality_after_verification_passed": true,
  "private_candidate_and_raw_logs_preserved": true,
  "temporary_synthetic_verifier_runtime_preserved": false,
  "main_bundle_processes_present_at_readback": false,
  "installed_main_replaced": false,
  "native_gui_launched": false,
  "existing_browser_profiles_used": false,
  "personal_career_content_used": false,
  "real_model_calls_made": false,
  "real_application_attempted": false,
  "human_acceptance_completed": false,
  "candidate_main_bundle_identity_matches": true,
  "signature_after_extension_rename_verified": true,
  "metadata_preserving_copy_tool_available": true,
  "synthetic_permission_check_file_scope_verified": true,
  "test_expectation_source_successor_frozen": true,
  "successor_only_requested_test_changed": true,
  "candidate_runtime_matches_source_successor": true,
  "candidate_native_inputs_match_source_successor": true,
  "new_boundary_tests_present_in_original_freeze": true
}
```

The candidate binds the existing freezer's complete allowlisted manifest. It
contains current source and synthetic inputs, including prior validated changes.
The installed main App was preserved. The verifier used temporary isolated
synthetic data; those temporary runtimes were cleaned up. Private raw logs and
the staged candidate remain available through the private evidence register.

## Parent-owned reversible installation recipe

This recipe is prepared only. Installation has not run.

1. Require the complete offline suite and repository gates to pass against the
   frozen source. Re-run freezer equality verification before integration.
2. Re-check the candidate signature and fixed main identity. Capture raw output
   privately. Verify the sole installation target is the documented main App.
3. Freshly query process arguments for the main bundle prefix. Include native,
   backend, Python, worker and helper processes. If any remain, stop before the
   swap; do not kill or resume real work as an installation shortcut.
4. With umask 077, create a new private rollback destination ending in
   `.bundle-rollback`, outside Applications. Use `/usr/bin/ditto --rsrc --extattr
   --acl` to copy the existing main bundle there. Verify the backup signature and
   full regular-file hashes against the original before changing the original.
   Preserve executable modes and symlinks. Do not blanket-chmod the bundle.
5. Copy the candidate to a fresh private staging destination with the same ditto
   flags. Verify its signature, executable identity and hashes against the sealed
   candidate. Do not register or launch the staging bundle.
6. Recheck process absence immediately before replacement. Move the existing main
   bundle to a private rollback location, then place the verified staged candidate
   at the sole main App path. Preserve the old bundle until final readback passes.
   A cross-filesystem move is not an atomic swap; record this limitation and use
   the verified independent rollback copy if any move or verification fails.
7. Verify installed signature, main identity and file hashes against candidate.
   Do not touch application support, configuration, task workspaces, browser
   profiles, attachments or career records.
8. Run only the fixed permission diagnostic with a fresh validated marker from
   the installed main identity. Do not launch the normal workspace route. Read
   the diagnostic's fresh private result and actual host/responsibility chain.
   Missing grants remain user action; never request grants in the diagnostic.
9. On replacement failure, ensure no candidate process remains, preserve the
   failed candidate privately, restore the verified rollback bytes to the sole
   main path with ditto, then verify signature and hashes again. Do not delete
   any rollback or real user state.

The fixed route selects `BackgroundCheckDelegate` before `AppDelegate` is
constructed. The synthetic file-scope check exercises the Python permission-only
checker using the existing fixture and an audit hook. It fails if that checker
opens anything outside its fresh synthetic root. Driver processes and grants are
mocked; fresh daemon temporary files are redirected inside that root. This is
software verification, not proof of live TCC grants or native acceptance.

## Test expectation successor

After the original equality readbacks, two test expectations were corrected in
`tests/test_resume_export.py`. A separate private source-successor manifest now
binds that version. Comparison confirms that this is the only changed file.
Every recorded bundled engine file and native build input still matches the
successor source. The original freeze and signed candidate remain preserved;
the artifact signature still verifies. No rebuild or installation was performed.
The original freeze already includes the three new observation, PDF recovery and
installed-policy boundary test files.

## Read-only legacy identity audit

```json
{
  "launchservices_audit_read_only": true,
  "legacy_registered_test_identity_found": true,
  "legacy_registered_test_executable_still_present_at_audit": true,
  "legacy_registered_path_resolves_to_retired_backup": false,
  "additional_repo_build_app_copies_found": true,
  "additional_repo_scratch_app_copies_found": true,
  "active_processes_for_audited_app_prefixes_found": false,
  "all_historical_build_executable_signatures_valid": false,
  "read_only_inventory_preserved_privately": true,
  "unregister_or_retirement_performed_by_auditor": false
}
```

The legacy test identity still resolves to an existing regular `.app`, so removing
a Settings row alone does not remove that rediscovery source. Exact-path
unregistration is a narrow useful cleanup after preservation and retirement of
the old bundle. The installed tool documents `-u` as unregister. Do not use a
database reset, seed, recursive scan or force registration. Unregistration cannot
guarantee that a permission row never returns, and it does not change TCC grants.

The inventory covers repository build outputs, repository TomorrowStar App
Info.plists and matching TomorrowStar LaunchServices identities. It excludes
upstream and dependency trees, and makes no global filesystem uniqueness claim.
One historical native executable failed signature verification; preserve it as
historical evidence rather than repairing or replacing its bytes.

## Post-retirement readback

```json
{
  "repository_tomorrowstar_app_copies_remaining": false,
  "only_existing_launchservices_app_path_is_canonical_main": true,
  "legacy_chrome_test_registration_present_in_fresh_dump": false,
  "stale_absent_path_registration_remains": true,
  "spotlight_existing_app_extension_matches_only_canonical_main": true,
  "spotlight_indexed_prior_bundle_backups_remain": true,
  "all_unregistration_attempts_passed": false,
  "all_launchservices_records_removed": false,
  "registration_or_launch_performed_by_auditor": false
}
```

The parent archived the old repository bundles. Fresh repository and
LaunchServices readback now identifies the canonical main path as the only
existing `.app` in the audited scope. One absent historical path remains in the
LaunchServices dump. Spotlight also retains earlier `.bundle-backup` entries;
these lack an `.app` extension but their preserved binaries remain recovery
artifacts. This does not claim the absence of every executable backup or a
global inventory of all disks.

Some targeted unregister calls reported `-10814` with `from spotlight`. The local
SDK identifies this as `kLSApplicationNotFoundErr`, which [Apple describes as no
matching application in the LaunchServices database](https://developer.apple.com/documentation/coreservices/3074489-anonymous/klsapplicationnotfounderr).
That failure is neither proof of a permission error nor proof of successful
unregistration. The exact post-retirement dump, path existence checks and
Spotlight metadata query provide the narrower current conclusion above.

## Parent final installation readback

The preparation receipts above remain historical. After the final normal-environment full offline suite passed, the parent updated only the fixed main installation, verified candidate bytes/modes and signature, and retained private rollback copies. The final nonprompt probe still reports both effective grants false. Legacy repository App copies were retired with restore maps; real applications remain paused. See [final engineering and concentrated user items](../remaining18-engineering-2026-10-20/README.md).
