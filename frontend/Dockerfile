# The client SPA: built with Vite, served by nginx with the API on the same
# origin. Two stages, so the image that ships is nginx plus a dist/ directory
# and none of node_modules.

FROM node:20-alpine AS build

WORKDIR /app

# Manifest first, so the dependency layer is cached until dependencies change.
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY . .
RUN npm run build


FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

# nginx's official entrypoint renders /etc/nginx/templates before starting, so
# the upstream is a deployment setting rather than a rebuild. Compose points it
# at the `app` service.
ENV CLIENT_API_UPSTREAM=app:5000 \
    CLIENT_DNS_RESOLVER=127.0.0.11
COPY nginx.conf /etc/nginx/templates/default.conf.template

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
