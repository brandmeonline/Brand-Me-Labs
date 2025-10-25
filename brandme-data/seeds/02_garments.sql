-- Copyright (c) Brand.Me, Inc. All rights reserved.
--
-- Seed Garments
-- Development and test garments

INSERT INTO garments (garment_id, creator_id, current_owner_id, display_name, category, description, cardano_asset_ref, authenticity_hash, public_esg_score, public_story_snippet, physical_tag_id, physical_tag_type, is_authentic, is_active, first_minted_at) VALUES
  -- Alice's creations
  (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '11111111-1111-1111-1111-111111111111', -- Alice
    '33333333-3333-3333-3333-333333333333', -- Charlie owns it
    'Midnight Silk Jacket',
    'jacket',
    'Hand-crafted silk jacket with sustainable dyes',
    'cardano_asset_midnight_jacket_001',
    'hash_a1b2c3d4e5f6g7h8i9j0',
    'A+',
    'Inspired by midnight skies over Tokyo, this jacket represents the fusion of tradition and innovation.',
    'NFC_TAG_001',
    'nfc',
    TRUE,
    TRUE,
    NOW() - INTERVAL '60 days'
  ),
  (
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    '11111111-1111-1111-1111-111111111111', -- Alice
    '11111111-1111-1111-1111-111111111111', -- Alice still owns
    'Urban Flow Sneakers',
    'sneakers',
    'Recycled materials, carbon-neutral production',
    'cardano_asset_urban_sneakers_002',
    'hash_k1l2m3n4o5p6q7r8s9t0',
    'A',
    'Designed for the modern urbanite who values both style and sustainability.',
    'QR_TAG_002',
    'qr',
    TRUE,
    TRUE,
    NOW() - INTERVAL '45 days'
  ),

  -- Bob's creations
  (
    'cccccccc-cccc-cccc-cccc-cccccccccccc',
    '22222222-2222-2222-2222-222222222222', -- Bob
    '44444444-4444-4444-4444-444444444444', -- Diana owns it
    'Heritage Leather Boots',
    'boots',
    'Artisanal leather boots with traditional craftsmanship',
    'cardano_asset_heritage_boots_003',
    'hash_u1v2w3x4y5z6a7b8c9d0',
    'B+',
    'Each pair tells a story of craftsmanship passed down through generations.',
    'NFC_TAG_003',
    'nfc',
    TRUE,
    TRUE,
    NOW() - INTERVAL '90 days'
  ),
  (
    'dddddddd-dddd-dddd-dddd-dddddddddddd',
    '22222222-2222-2222-2222-222222222222', -- Bob
    '22222222-2222-2222-2222-222222222222', -- Bob still owns
    'Eco-Tech Backpack',
    'accessories',
    'High-tech backpack with solar panels and recycled materials',
    'cardano_asset_ecotech_backpack_004',
    'hash_e1f2g3h4i5j6k7l8m9n0',
    'A+',
    'Function meets sustainability in this innovative backpack design.',
    'QR_TAG_004',
    'qr',
    TRUE,
    TRUE,
    NOW() - INTERVAL '30 days'
  )
ON CONFLICT (garment_id) DO NOTHING;
