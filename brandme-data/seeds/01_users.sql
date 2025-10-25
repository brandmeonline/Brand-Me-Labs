-- Copyright (c) Brand.Me, Inc. All rights reserved.
--
-- Seed Users
-- Development and test user accounts

INSERT INTO users (user_id, handle, display_name, email, region_code, persona_warm_cold, persona_sport_couture, trust_score, oauth_provider, oauth_provider_id, is_active, is_verified) VALUES
  -- Creator users
  ('11111111-1111-1111-1111-111111111111', 'alice_creator', 'Alice Designer', 'alice@example.com', 'us-east1', 0.75, 0.85, 95.50, 'google', 'google_alice_123', TRUE, TRUE),
  ('22222222-2222-2222-2222-222222222222', 'bob_artisan', 'Bob Artisan', 'bob@example.com', 'us-east1', 0.60, 0.70, 88.25, 'google', 'google_bob_456', TRUE, TRUE),

  -- Owner users
  ('33333333-3333-3333-3333-333333333333', 'charlie_collector', 'Charlie Collector', 'charlie@example.com', 'us-east1', 0.50, 0.90, 92.00, 'github', 'github_charlie_789', TRUE, TRUE),
  ('44444444-4444-4444-4444-444444444444', 'diana_enthusiast', 'Diana Enthusiast', 'diana@example.com', 'us-west1', 0.80, 0.60, 78.50, 'google', 'google_diana_321', TRUE, TRUE),

  -- Scanner users (general public)
  ('55555555-5555-5555-5555-555555555555', 'eve_scanner', 'Eve Scanner', 'eve@example.com', 'us-east1', 0.45, 0.55, 65.00, 'google', 'google_eve_654', TRUE, TRUE),
  ('66666666-6666-6666-6666-666666666666', 'frank_curious', 'Frank Curious', 'frank@example.com', 'eu-west1', 0.70, 0.50, 72.25, 'google', 'google_frank_987', TRUE, TRUE),

  -- Governance & Compliance users
  ('77777777-7777-7777-7777-777777777777', 'gov_admin', 'Governance Admin', 'gov@brandme.com', 'us-east1', NULL, NULL, 100.00, 'google', 'google_gov_111', TRUE, TRUE),
  ('88888888-8888-8888-8888-888888888888', 'compliance_agent', 'Compliance Agent', 'compliance@brandme.com', 'us-east1', NULL, NULL, 100.00, 'google', 'google_compliance_222', TRUE, TRUE)
ON CONFLICT (user_id) DO NOTHING;

-- Update timestamps for test users
UPDATE users
SET created_at = NOW() - INTERVAL '30 days',
    last_login_at = NOW() - INTERVAL '1 day'
WHERE user_id IN (
  '11111111-1111-1111-1111-111111111111',
  '22222222-2222-2222-2222-222222222222',
  '33333333-3333-3333-3333-333333333333'
);
