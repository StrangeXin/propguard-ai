-- PropGuard AI — User-supplied MetaApi API tokens for ownership proof.
-- Stored AES-GCM encrypted at rest; backend holds the key in env
-- METAAPI_TOKEN_ENC_KEY (base64-encoded 32 bytes). Rotating the key
-- invalidates stored tokens (users re-bind).

alter table users
  add column if not exists metaapi_user_token_encrypted text;
