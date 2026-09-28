FROM node:22.23.3-alpine3.24 AS build
WORKDIR /src
COPY greencity-app/package.json greencity-app/package-lock.json ./
RUN npm ci
COPY greencity-app/ ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.30.5-alpine3.24
COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
