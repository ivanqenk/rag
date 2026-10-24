# Imagen del frontend: compila la aplicación con Node y la sirve con nginx (sin Node en
# producción). nginx también hace de proxy de /api hacia el backend.

FROM node:24.19-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# Variante oficial de nginx que se ejecuta sin root (puerto 8080).
FROM nginxinc/nginx-unprivileged:1.31-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 8080
