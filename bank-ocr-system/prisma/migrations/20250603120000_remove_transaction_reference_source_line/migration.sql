-- Drop unused transaction columns (reference, sourceLine)
ALTER TABLE "Transaction" DROP COLUMN IF EXISTS "reference";
ALTER TABLE "Transaction" DROP COLUMN IF EXISTS "sourceLine";
