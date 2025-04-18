```
!curl -i -X POST \
  -H "Content-Type: application/json" \
  -d '{"A": 1, "B": 1, "C": 1, "G": 1, "H": 1, "I": 1}' \
  https://minimum-delivery-cost.onrender.com/calculate
```
```
HTTP/2 200 
date: Fri, 18 Apr 2025 17:43:35 GMT
content-type: application/json
rndr-id: ff770810-9eb2-44d5
vary: Accept-Encoding
x-render-origin-server: gunicorn
cf-cache-status: DYNAMIC
server: cloudflare
cf-ray: 9325f71ec9ddf5ca-IAD
alt-svc: h3=":443"; ma=86400

{"minimum_cost":118}
```
