# Download Jobs and Directory Shares

> These are source-candidate features, not included in the published PyPI `0.2.8` package. A new package version follows live-candidate acceptance.

After signing in to a directory through `chatshare serve`, two Chinese-first controls are available:

- **从链接下载 (Download from link)** accepts one direct HTTP/HTTPS file URL and a relative destination. The destination starts at the current directory; append a file name before submitting. A job ID is returned immediately. The page reports queued, downloading, committing, completed, failed, cancelled, or restart-interrupted state, real bytes, known/unknown total, and speed. Reloading retains job history.
- **分享当前目录 (Share current directory)** creates an independent link for an existing writable directory. The link is a 256-bit bearer capability: anyone holding it can browse that directory and descendants. Send it only to trusted recipients and revoke it when finished.

Capability visitors get read-only directory browsing—no search, zip, upload, management, or job access. Directory navigation remains under the capability route, while file anchors always retain the original URI. Revocation immediately closes browsing but does not revoke already-public concrete file URLs.

## API

Browser APIs reuse the ChatLogin session. Every mutation additionally requires the same-origin `Origin` and `X-CSRF-Token`:

- `POST/GET /_chatshare/downloads` creates or lists the owner's jobs.
- `GET/DELETE /_chatshare/downloads/<id>` reads or cancels an owner job.
- `POST/GET /_chatshare/shares` creates or lists owner directory shares.
- `DELETE /_chatshare/shares/<id>` revokes an owner share.

Download JSON is `{"url":"https://…","target":"directory/file"}`; share JSON is `{"directory":"/directory/"}`. Admission and final publication each query real Dufs metadata for the exact target, expected user, and `allow_upload`; share creation requires the exact directory to exist. No CLI command is added.

## Defaults and storage

The worker pool uses concurrency 2, at most 20 active jobs, a 20 GiB file maximum, 5-second connect timeout, 30-second download-idle timeout, and 5 redirects. Up to 200 status records are retained. Private `downloads/` and `shares/` state lives under the effective `ChatSharePaths.base`, with `0700` directories and `0600` metadata. URL query/path secrets and writer credentials are never persisted. Deployment storage must place private staging and the share root on one filesystem for atomic no-overwrite publication.
