-- Overstay alerting needs to remember that it already warned about a given stay.
--
-- Persisted rather than kept in memory on purpose. The previous build tracked this in a
-- process-local dict, so every restart re-alerted the dispatcher about everyone still on
-- site - the same class of problem as an in-memory strictness flag silently reverting
-- (REBUILD_PROMPT §0.6.6): state that matters has to survive the process that made it.
--
-- Cleared on exit, so a person's next visit is a fresh stay and can alert again.
ALTER TABLE people ADD COLUMN overstay_alerted_at TEXT NOT NULL DEFAULT '';
