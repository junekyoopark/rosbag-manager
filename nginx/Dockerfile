FROM nginx:1.25-alpine
RUN apk add --no-cache gettext     # provides envsubst
COPY nginx.conf.http      /etc/nginx/nginx.conf.http
COPY nginx.conf.template  /etc/nginx/nginx.conf.template
COPY entrypoint.sh        /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
