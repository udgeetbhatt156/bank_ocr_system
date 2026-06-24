# Use Node 20
FROM node:20-alpine

# Set working directory
WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
COPY prisma ./prisma
RUN npm install

# Copy rest of the project
COPY . .

# Build Next.js app
RUN npm run build

# Expose app port
EXPOSE 3000

# Apply database migrations, then start app
CMD ["sh", "-c", "npm run db:migrate && npm start"]
