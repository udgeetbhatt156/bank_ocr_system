-- Drop unused transaction columns (reference, sourceLine)
ALTER TABLE IF EXISTS "Transaction" DROP COLUMN IF EXISTS "reference";
ALTER TABLE IF EXISTS "Transaction" DROP COLUMN IF EXISTS "sourceLine";
