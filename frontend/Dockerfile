# EDI-Converter frontend image — build with Node, serve the static output from
# an unprivileged nginx. Nothing from the build stage (node_modules, the Node
# runtime, the TypeScript compiler) reaches the final image: it ships only the
# compiled bundle.

# --------------------------------------------------------------------------- #
#  Stage 1 — build the static bundle
# --------------------------------------------------------------------------- #
FROM node:20-alpine AS build

WORKDIR /app

# `npm ci` (not `npm install`) installs exactly what package-lock.json pins, so
# the image is reproducible and the build cannot silently drift to new versions.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# URL the browser uses to reach the backend, baked in at build time.
ARG VITE_API_URL=http://localhost:5080
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# --------------------------------------------------------------------------- #
#  Stage 2 — serve
# --------------------------------------------------------------------------- #
# The unprivileged variant runs as uid 101 and listens on 8080, so the container
# needs no root and no NET_BIND_SERVICE capability.
FROM nginxinc/nginx-unprivileged:alpine AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

# 127.0.0.1, not localhost: /etc/hosts resolves localhost to ::1 first and nginx
# binds IPv4 only, so the IPv6 attempt is refused and the check never passes.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:8080/ || exit 1
