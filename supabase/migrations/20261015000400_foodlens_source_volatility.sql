-- Timestamptz JSON formatting follows the session timezone, hence STABLE.
alter function foodlens_private.public_source_evidence(jsonb,timestamptz) stable;
