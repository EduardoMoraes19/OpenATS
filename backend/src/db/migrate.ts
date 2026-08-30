import "dotenv/config";
import { Pool } from "pg";
import { drizzle } from "drizzle-orm/node-postgres";
import { migrate } from "drizzle-orm/node-postgres/migrator";
import logger from "../utils/logger";

/**
 * Applies the committed migrations in `backend/drizzle`.
 *
 * Deliberately uses drizzle-orm's own migrator rather than `drizzle-kit
 * migrate` — drizzle-kit is a devDependency and reads a TypeScript config, so
 * running it in production would mean shipping the dev toolchain in the image.
 */
async function main() {
  const pool = new Pool({ connectionString: process.env.DATABASE_URL });

  try {
    await migrate(drizzle(pool), { migrationsFolder: "./drizzle" });
    logger.info("Migrations applied.");
  } finally {
    await pool.end();
  }
}

main().catch((err) => {
  logger.error("Migration failed:", err);
  process.exit(1);
});
