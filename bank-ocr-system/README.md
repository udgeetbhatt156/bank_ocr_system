# bank-orc-client

## Local database setup

This project uses PostgreSQL through Prisma. For local development, you can run
Postgres in Docker.

### 1. Start local Postgres

```bash
docker run --name ocr-postgres \
  --network bridge \
  -e POSTGRES_DB=ocr \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD="add your password" \
  -p 5433:5432 \
  -d postgres:18
```

If the container already exists, start it again with:

```bash
docker start ocr-postgres
```

If you need to recreate it:

```bash
docker rm -f ocr-postgres
```

Then run the `docker run` command again.

### 2. Configure `.env`

When running the Next.js app directly on your machine with `npm run dev`, use
`localhost:5433`:

```env
DATABASE_URL="postgresql://postgres:password@localhost:5433/ocr"
JWT_SECRET_KEY="bank-ocr-secret-key-10011"
JWT_SECRET="bank-ocr-secret-key-10011"
```

When running the app inside Docker on the same Docker network as Postgres, use
the container name and internal Postgres port:

```env
DATABASE_URL="postgresql://postgres:password@ocr-postgres:5432/ocr"
```

Use `5433` only from the host machine. Use `5432` between Docker containers.

### 3. Install dependencies

```bash
npm install
```

### 4. Apply Prisma migrations

```bash
npm run db:migrate
```

For local development, if you want Prisma to sync the schema directly instead:

```bash
npm run db:push
```

### 5. Run the app locally

```bash
npm run dev
```

The app should be available at:

```text
http://localhost:3000
```

## Useful Docker commands

Check running containers:

```bash
docker ps
```

View Postgres logs:

```bash
docker logs ocr-postgres
```

Connect an app container and Postgres container to the same Docker network:

```bash
docker network create ocr-network
docker network connect ocr-network ocr-postgres
```
