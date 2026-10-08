/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * GET/PATCH /api/v1/me — current member, settings, onboarding state and
 * capability summary. PATCH requires If-Match and only allowlisted fields
 * (MePatch in @brandme/contracts); a stale revision gets 409 with the current
 * revision, never a silent last-write-wins.
 */

import { Router, type Request, type Response } from 'express';
import type { GatewayConfig } from '../../config';
import { DEV_IDENTITY_LABEL } from '../../middleware/mode';
import { handle, problems } from '../../middleware/problem';
import { requirePrincipal } from '../../middleware/session';
import { HandleTakenError, IdentityStore, MemberInactiveError, VersionConflictError, type MePatch } from '../../middleware/identity/store';
import type { Principal } from '../../types';
import { validator } from '../../middleware/validation';

const validateMePatch = validator('MePatch');

export function parseIfMatch(header: string | undefined): number {
  if (!header) throw problems.preconditionRequired();
  const m = /^(?:W\/)?"?(\d{1,18})"?$/.exec(header.trim());
  if (!m) throw problems.preconditionRequired();
  return Number(m[1]);
}

export function capabilitySummary(principal: Principal) {
  return [
    {
      name: 'auth.identity',
      state: principal.assuranceLevel === 'simulated' ? 'simulated' : 'available',
      reason_code: principal.assuranceLevel === 'simulated' ? 'dev_identity_provider' : 'oidc_verified',
      simulation_label: principal.assuranceLevel === 'simulated' ? DEV_IDENTITY_LABEL : null,
    },
    { name: 'profile.persistence', state: 'available', reason_code: 'spanner', simulation_label: null },
    // Commerce, rights and try-on are reported by their owning lanes' registries;
    // until those merge they are unconfigured, not implied available.
    { name: 'commerce.checkout', state: 'unconfigured', reason_code: 'lane_not_integrated', simulation_label: null },
    { name: 'rights.transfer', state: 'unconfigured', reason_code: 'lane_not_integrated', simulation_label: null },
    { name: 'tryon.photo', state: 'unconfigured', reason_code: 'lane_not_integrated', simulation_label: null },
  ];
}

async function loadMe(store: IdentityStore, cfg: GatewayConfig, principal: Principal) {
  const found = await store.getMember(principal.memberId);
  if (!found) throw problems.notFound();
  const { member, settings } = found;
  return {
    body: {
      member: {
        id: member.member_id,
        handle: member.handle,
        display_name: member.display_name,
        locale: member.locale,
        timezone: member.timezone,
        age_eligibility_status: member.age_eligibility_status,
        account_state: member.account_state,
        version: String(member.version),
        created_at: member.created_at,
        updated_at: member.updated_at,
      },
      settings: {
        room_theme: settings.room_theme,
        motion_mode: settings.motion_mode,
        quality_mode: settings.quality_mode,
        default_visibility: settings.default_visibility,
        notification_preferences: { in_app: settings.notify_in_app, email: settings.notify_email, push: settings.notify_push },
        version: String(settings.version),
      },
      onboarding_state: member.onboarding_state,
      environment: cfg.mode,
      session: {
        assurance_level: principal.assuranceLevel,
        identity_provider: principal.identityProvider,
        expires_at: principal.expiresAt.toISOString(),
      },
      capabilities: capabilitySummary(principal),
    },
    version: member.version,
  };
}

export function meRouter(cfg: GatewayConfig, store: IdentityStore): Router {
  const router = Router();
  router.use(requirePrincipal);

  router.get(
    '/',
    handle(async (_req: Request, res: Response) => {
      const { body, version } = await loadMe(store, cfg, res.locals.principal);
      res.setHeader('ETag', `"${version}"`);
      res.json(body);
    }),
  );

  router.patch(
    '/',
    handle(async (req: Request, res: Response) => {
      const expected = parseIfMatch(req.header('if-match'));
      if (!validateMePatch(req.body)) {
        throw problems.invalid((validateMePatch.errors ?? []).map((e) => `${e.instancePath || 'body'} ${e.message}`).join('; '));
      }
      const principal: Principal = res.locals.principal;
      try {
        await store.patchMember(principal.memberId, expected, req.body as MePatch, res.locals.requestId);
      } catch (err) {
        if (err instanceof VersionConflictError) {
          throw problems.conflict('The profile changed since you loaded it. Reload to merge your edits.', { current_version: String(err.currentVersion) });
        }
        if (err instanceof HandleTakenError) throw problems.invalid('That handle is not available.');
        if (err instanceof MemberInactiveError) throw problems.notFound();
        throw err;
      }
      const { body, version } = await loadMe(store, cfg, principal);
      res.setHeader('ETag', `"${version}"`);
      res.json(body);
    }),
  );

  return router;
}
