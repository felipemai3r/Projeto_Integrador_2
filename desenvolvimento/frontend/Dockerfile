# Build do front (Node) e servico dos arquivos estaticos (Nginx).
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/seguranca.conf /etc/nginx/seguranca.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
