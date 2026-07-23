---
tags: [auth, security]
---
# Auth System
Sessions are JWT with a 15-minute access token + rotating refresh token.
We decided against magic links because support couldn't handle the reset volume.
