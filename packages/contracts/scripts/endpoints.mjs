// Endpoint inventory from docs/design/brandme/03-architecture-data-api.md §6.
// `owner` is the lane expected to implement the operation; `status`
// "implemented" only where code exists in this repository and is tested.
// Body/response names refer to domain.schema.json $defs or foundation
// extensions; a missing response means the owning lane defines it first.

const E = (method, path, id, tag, owner, extra = {}) => ({ method, path, id, tag, owner, summary: extra.summary ?? id, ...extra });

export const ENDPOINTS = [
  // Foundation (identity/session/system)
  E('get', '/me', 'getMe', 'identity', 'foundation', { response: 'Me', status: 'implemented', summary: 'Current member, settings, onboarding state and capability summary' }),
  E('patch', '/me', 'patchMe', 'identity', 'foundation', { body: 'MePatch', response: 'Me', ifMatch: true, status: 'implemented', summary: 'Allowlisted profile fields with If-Match' }),
  E('post', '/session/dev', 'createDevSession', 'identity', 'foundation', { body: 'DevSessionCreate', response: 'SessionInfo', created: true, public: true, status: 'implemented', summary: 'demo/development only: session for a fictional test identity' }),
  E('get', '/session', 'getSession', 'identity', 'foundation', { response: 'SessionInfo', status: 'implemented' }),
  E('delete', '/session', 'deleteSession', 'identity', 'foundation', { noContent: true, status: 'implemented', summary: 'Sign out; revokes the session server-side' }),
  E('get', '/system/health', 'getSystemHealth', 'system', 'foundation', { response: 'SystemHealth', public: true, status: 'implemented', summary: 'Gateway → brain → persistence smoke' }),
  E('get', '/capabilities', 'getCapabilities', 'system', 'foundation', { response: 'CapabilitySummaryEntry', list: true }),

  // Persona
  E('get', '/me/persona', 'getPersona', 'persona', 'consumer-domains', { response: 'PersonaProfile' }),
  E('patch', '/me/persona', 'patchPersona', 'persona', 'consumer-domains', { body: 'PersonaPatch', response: 'PersonaProfile', ifMatch: true }),
  E('post', '/me/persona/preview', 'previewPersona', 'persona', 'consumer-domains', { body: 'PersonaPatch' }),
  E('get', '/me/persona/evidence', 'listPersonaEvidence', 'persona', 'consumer-domains', { paginated: true }),
  E('post', '/me/persona/evidence/{evidenceId}/suppress', 'suppressPersonaEvidence', 'persona', 'consumer-domains', { idempotent: true }),
  E('post', '/me/persona/reset', 'resetPersona', 'persona', 'consumer-domains', { ifMatch: true, idempotent: true }),
  E('post', '/me/persona/snapshots', 'createPersonaSnapshot', 'persona', 'consumer-domains', { idempotent: true, created: true }),
  E('get', '/recommendations', 'listRecommendations', 'persona', 'consumer-domains', { paginated: true }),
  E('post', '/recommendations/{recommendationId}/feedback', 'recommendationFeedback', 'persona', 'consumer-domains', { idempotent: true }),

  // Catalog / media
  E('get', '/catalog/search', 'searchCatalog', 'catalog', 'commerce-agents', { paginated: true }),
  E('get', '/catalog/products/{productId}', 'getCatalogProduct', 'catalog', 'commerce-agents'),
  E('post', '/media/uploads', 'createMediaUpload', 'media', 'consumer-domains', { idempotent: true, created: true }),
  E('get', '/media/jobs/{jobId}', 'getMediaJob', 'media', 'consumer-domains'),

  // Wardrobe / closet / outfits
  E('get', '/wardrobe/items', 'listWardrobeItems', 'wardrobe', 'consumer-domains', { response: 'WardrobeItem', list: true, paginated: true }),
  E('post', '/wardrobe/items', 'createWardrobeItem', 'wardrobe', 'consumer-domains', { response: 'WardrobeItem', idempotent: true, created: true }),
  E('patch', '/wardrobe/items/{itemId}', 'patchWardrobeItem', 'wardrobe', 'consumer-domains', { response: 'WardrobeItem', ifMatch: true }),
  E('post', '/wardrobe/items/{itemId}/archive', 'archiveWardrobeItem', 'wardrobe', 'consumer-domains', { ifMatch: true, idempotent: true }),
  E('get', '/closet/layout', 'getClosetLayout', 'closet', 'spatial-ar'),
  E('put', '/closet/layout/theme', 'putClosetTheme', 'closet', 'spatial-ar', { ifMatch: true }),
  E('put', '/closet/placements/{itemId}', 'putClosetPlacement', 'closet', 'spatial-ar', { body: 'ClosetPlacement', response: 'ClosetPlacement', ifMatch: true }),
  E('post', '/closet/placements/batch', 'batchClosetPlacements', 'closet', 'spatial-ar', { idempotent: true }),
  E('get', '/outfits', 'listOutfits', 'outfits', 'consumer-domains', { paginated: true }),
  E('post', '/outfits', 'createOutfit', 'outfits', 'consumer-domains', { idempotent: true, created: true }),
  E('post', '/outfits/{outfitId}/versions', 'createOutfitVersion', 'outfits', 'consumer-domains', { ifMatch: true, created: true }),
  E('post', '/outfits/{outfitId}/proposals', 'proposeOutfit', 'outfits', 'consumer-domains', { idempotent: true, created: true }),

  // Social
  E('get', '/relationships', 'listRelationships', 'social', 'consumer-domains', { paginated: true }),
  E('post', '/relationships', 'requestRelationship', 'social', 'consumer-domains', { idempotent: true, created: true }),
  E('post', '/relationships/{relationshipId}/accept', 'acceptRelationship', 'social', 'consumer-domains', { idempotent: true }),
  E('post', '/members/{memberId}/block', 'blockMember', 'social', 'consumer-domains', { idempotent: true }),
  E('get', '/decisions', 'listDecisions', 'social', 'consumer-domains', { paginated: true }),
  E('post', '/decisions', 'createDecision', 'social', 'consumer-domains', { body: 'DecisionCreate', idempotent: true, created: true }),
  E('post', '/decisions/{decisionId}/responses', 'respondToDecision', 'social', 'consumer-domains', { body: 'DecisionResponse', idempotent: true }),
  E('post', '/decisions/{decisionId}/close', 'closeDecision', 'social', 'consumer-domains', { idempotent: true }),
  E('post', '/shares', 'createShare', 'social', 'consumer-domains', { body: 'ShareCreate', idempotent: true, created: true }),
  E('delete', '/shares/{shareId}', 'revokeShare', 'social', 'consumer-domains', { noContent: true }),
  E('get', '/notifications', 'listNotifications', 'social', 'consumer-domains', { paginated: true }),
  E('post', '/notifications/read', 'markNotificationsRead', 'social', 'consumer-domains'),

  // Rewards
  E('get', '/rewards', 'getRewards', 'rewards', 'consumer-domains'),
  E('post', '/benefits/{benefitId}/reservations', 'reserveBenefit', 'rewards', 'consumer-domains', { idempotent: true, created: true }),

  // Assistant / commerce
  E('post', '/assistant/tasks', 'createAssistantTask', 'assistant', 'commerce-agents', { idempotent: true, accepted: true }),
  E('get', '/assistant/tasks/{taskId}/events', 'streamAssistantTaskEvents', 'assistant', 'commerce-agents'),
  E('post', '/assistant/tasks/{taskId}/cancel', 'cancelAssistantTask', 'assistant', 'commerce-agents', { idempotent: true }),
  E('get', '/delegations', 'listDelegations', 'commerce', 'commerce-agents'),
  E('post', '/delegations', 'createDelegation', 'commerce', 'commerce-agents', { idempotent: true, created: true }),
  E('delete', '/delegations/{delegationId}', 'revokeDelegation', 'commerce', 'commerce-agents', { noContent: true }),
  E('post', '/commerce/carts', 'createCart', 'commerce', 'commerce-agents', { idempotent: true, created: true }),
  E('patch', '/commerce/carts/{cartId}', 'patchCart', 'commerce', 'commerce-agents', { ifMatch: true }),
  E('post', '/commerce/carts/{cartId}/quote', 'quoteCart', 'commerce', 'commerce-agents', { response: 'CheckoutQuote', idempotent: true }),
  E('post', '/commerce/approvals', 'createPurchaseApproval', 'commerce', 'commerce-agents', { idempotent: true, created: true }),
  E('post', '/commerce/purchases', 'createPurchase', 'commerce', 'commerce-agents', { body: 'PurchaseRequest', idempotent: true, accepted: true }),
  E('get', '/commerce/orders/{orderId}', 'getOrder', 'commerce', 'commerce-agents'),
  E('post', '/commerce/orders/{orderId}/returns', 'requestReturn', 'commerce', 'commerce-agents', { idempotent: true, accepted: true }),

  // Ownership / rights / chain
  E('get', '/assets/{assetId}/passport', 'getPassport', 'rights', 'midnight-rights'),
  E('post', '/assets/{assetId}/claims', 'submitClaim', 'rights', 'midnight-rights', { idempotent: true, accepted: true }),
  E('post', '/assets/{assetId}/transfers', 'createTransfer', 'rights', 'midnight-rights', { idempotent: true, created: true }),
  E('post', '/transfers/{transferId}/accept', 'acceptTransfer', 'rights', 'midnight-rights', { idempotent: true }),
  E('get', '/chain/operations/{operationId}', 'getChainOperation', 'rights', 'midnight-rights', { response: 'ChainOperation' }),
  E('post', '/assets/{assetId}/reprint-quotes', 'createReprintQuote', 'rights', 'midnight-rights', { idempotent: true }),
  E('post', '/reprint-jobs', 'createReprintJob', 'rights', 'midnight-rights', { idempotent: true, accepted: true }),

  // Try-on
  E('post', '/try-on/jobs', 'createTryOnJob', 'try-on', 'spatial-ar', { idempotent: true, accepted: true }),
  E('delete', '/try-on/jobs/{jobId}', 'deleteTryOnJob', 'try-on', 'spatial-ar', { noContent: true }),

  // Privacy
  E('get', '/me/consents', 'listConsents', 'privacy', 'foundation'),
  E('post', '/me/consents', 'grantConsent', 'privacy', 'foundation', { idempotent: true, created: true }),
  E('delete', '/me/consents/{consentId}', 'revokeConsent', 'privacy', 'foundation', { noContent: true }),
  E('post', '/me/exports', 'requestExport', 'privacy', 'foundation', { idempotent: true, accepted: true }),
  E('post', '/me/deletion', 'requestDeletion', 'privacy', 'foundation', { idempotent: true, accepted: true }),
];
