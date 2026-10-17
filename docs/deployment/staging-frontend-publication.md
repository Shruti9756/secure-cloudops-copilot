# First staging static-website publication

**First publication completed and operator-verified on 17 October 2026.**
All 29 reviewed objects passed upload/storage checks, and both public HTML
routes returned HTTP 200. This does not establish working browser sign-in,
API connectivity, or AI functionality, and does not authorize Terraform
applies, API attachment, or starting runtime services.

**Do not rerun the first-publication upload block.** The bucket is now
populated; that block required an empty destination. Keep it as the record
of the original operation. Future updates require a separate reviewed plan.

## 1. What the reviewed preview proved

The operator's dry run confirmed the reviewed 29-file export, the expected
AWS account, and deployed distribution `E2JZ8IOOSQ6MB9` at
`https://d28yij2tl8eb0p.cloudfront.net`. The distribution had one origin:
the private frontend bucket, with no additional API cache behavior.
The owner-checked bucket listing returned no objects, and all 29 proposed
uploads targeted that same bucket. No upload/deletion occurred in that preview.

| Item | This first publication only |
| --- | --- |
| Local source | `C:\Users\Shru\Documents\AI+AWS\apps\web\out` |
| Destination | `secure-cloudops-staging-web-291667884598-us-east-1` |
| Account / region / profile | `291667884598` / `us-east-1` / `securecloudops-dev` |
| Reviewed files / bytes | `29` / `721310` |
| Reviewed export fingerprint | `e7b80e375379e925c397a1e32770ec192401e90dd511145cc3c59b80c133c1a7` |

Only the generated website is published. `.env.local`, source files,
Terraform files/state, documents, and credentials must never be uploaded.
Do not rebuild or edit the export while running this procedure. A changed
fingerprint needs a fresh review, not a replacement expected hash.

**Two concepts used below:**

- Content type tells the browser whether a file is HTML, JavaScript, CSS,
  or plain text. Explicit types avoid depending on Windows MIME guesses.
  The generated `.txt` files are needed by Next.js; do not exclude them.
- Cache control tells browsers/intermediaries how to reuse saved copies.
  Version-named `_next/static/` assets get long-lived immutable caching;
  HTML and Next.js text request revalidation. CloudFront's current
  `CachingOptimized` policy still has a one-second minimum TTL, so this
  does not promise a fresh origin request for every view. See
  [AWS managed cache policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-cache-policies.html).

This uses the existing S3/CloudFront resources and can incur storage/request
charges. It does not provision or start Fargate, RDS, Valkey, or an ALB.

### Verified publication results — 17 October 2026

The operator explicitly confirmed `PUBLISH STAGING` and reported:

- 13 JavaScript/CSS assets uploaded first, then 12 Next.js text files,
  then four HTML files; `index.html` was last.
- Every object passed the supplied SHA-256 checksum and stored size,
  content-type, cache-control, and AES256-encryption checks.
- The final bucket inventory matched exactly the 29 reviewed keys/sizes.
- Final upload message: `PASS: 29 reviewed website objects uploaded and verified. Runtime services were not started.`
- `https://d28yij2tl8eb0p.cloudfront.net/` returned HTTP 200 HTML.
- `https://d28yij2tl8eb0p.cloudfront.net/auth/callback.html` returned HTTP 200 HTML.

These are the operator's reported results from the guarded procedure below,
not a separate independent AWS audit. No invalidation, Terraform apply,
API attachment, or runtime-start command was part of this operation.

### Read-only browser rendering check — 17 October 2026

A separate browser check observed the styled dashboard at a 1280-by-720
viewport, loaded its same-origin stylesheet, and found no horizontal
overflow. The captured console contained no warnings/errors. Workspace
guidance and disabled upload controls matched the anonymous initial state.
The operational/service labels are static demo content, not live AWS health.

Opening `/auth/callback.html` without login parameters changed from the
preparing state to the expected "Sign-in was not completed" state. This
demonstrates execution of the callback's client-side JavaScript, not a real
Cognito sign-in attempt or authentication failure. No sign-in, workspace,
refresh, upload, or question action was invoked. These limited rendering
checks do not verify all assets, responsive sizes, or authenticated flows.

## 2. Historical first-publication block — completed; do not rerun

The following is the original operator-run block, retained for reference.
Its preflight checked the export, account, static-only distribution, bucket
public-access protection, ACL-disabled ownership, default AES256 encryption,
and empty destination. The operator then typed `PUBLISH STAGING` to proceed.

Uploads are create-only: each request supplies the expected bucket owner,
`If-None-Match: *`, and the reviewed file's SHA-256 checksum. S3 rejects an
existing key or mismatched bytes. Assets arrive first, then Next.js text,
then HTML, with `index.html` last. Every accepted object is checked for
checksum, size, content type, cache control, and AES256 encryption.
See [AWS conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html)
and [PutObject](https://docs.aws.amazon.com/cli/latest/reference/s3api/put-object.html).

There is no delete, ACL change, public-bucket setting, invalidation,
Terraform command, or ECS start in this block.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $frontendOut = 'C:\Users\Shru\Documents\AI+AWS\apps\web\out'
    $frontendBucket = 'secure-cloudops-staging-web-291667884598-us-east-1'
    $expectedFingerprint = 'e7b80e375379e925c397a1e32770ec192401e90dd511145cc3c59b80c133c1a7'

    function Invoke-FrontendAwsJson {
        param([string[]]$AwsArguments)
        $jsonText = & aws @AwsArguments --profile securecloudops-dev --region us-east-1 --output json --no-cli-pager
        if ($LASTEXITCODE -ne 0) {
            throw "AWS command failed: $($AwsArguments[0]) $($AwsArguments[1]). Stop; do not restart the publication block."
        }
        return (($jsonText -join [char]10) | ConvertFrom-Json)
    }

    $rootEntry = Get-Item -LiteralPath $frontendOut -Force
    $entries = @(Get-ChildItem -LiteralPath $frontendOut -Recurse -Force)
    if (@(@($rootEntry) + $entries | Where-Object {
        ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
    }).Count -gt 0) {
        throw 'Export contains a link. Stop here.'
    }

    $contentTypes = @{
        '.js' = 'text/javascript; charset=utf-8'
        '.css' = 'text/css; charset=utf-8'
        '.txt' = 'text/plain; charset=utf-8'
        '.html' = 'text/html; charset=utf-8'
    }
    $uploadFiles = @(
        $entries | Where-Object { -not $_.PSIsContainer } | Sort-Object FullName | ForEach-Object {
            if (-not $contentTypes.ContainsKey($_.Extension)) {
                throw "Unexpected export file: $($_.Name)"
            }
            $key = $_.FullName.Substring($frontendOut.Length + 1).Replace('\', '/')
            $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
            [byte[]]$hashBytes = @(for ($n = 0; $n -lt $hash.Length; $n += 2) {
                [Convert]::ToByte($hash.Substring($n, 2), 16)
            })
            $order = 2
            $cacheControl = 'public,max-age=0,must-revalidate'
            if ($key.StartsWith('_next/static/')) {
                $order = 0
                $cacheControl = 'public,max-age=31536000,immutable'
            } elseif ($_.Extension -eq '.txt') {
                $order = 1
            } elseif ($key -eq 'index.html') {
                $order = 3
            }
            [pscustomobject]@{
                Path = $_.FullName
                Key = $key
                Bytes = $_.Length
                Hash = $hash
                Checksum = [Convert]::ToBase64String($hashBytes)
                ContentType = $contentTypes[$_.Extension]
                CacheControl = $cacheControl
                Order = $order
            }
        }
    )
    $manifest = @($uploadFiles | ForEach-Object { '{0}|{1}|{2}' -f $_.Key, $_.Bytes, $_.Hash })
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $fingerprint = [BitConverter]::ToString(
            $hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes(($manifest -join [char]10)))
        ).Replace('-', '').ToLowerInvariant()
    }
    finally { $hasher.Dispose() }
    if ($fingerprint -ne $expectedFingerprint -or $uploadFiles.Count -ne 29) {
        throw 'The export differs from the reviewed 29 files. Stop here.'
    }

    $identity = Invoke-FrontendAwsJson -AwsArguments @('sts', 'get-caller-identity')
    if ($identity.Account -ne '291667884598') { throw 'Wrong AWS account.' }

    $distribution = Invoke-FrontendAwsJson -AwsArguments @(
        'cloudfront', 'get-distribution', '--id', 'E2JZ8IOOSQ6MB9', '--query',
        'Distribution.{Arn:ARN,Status:Status,Domain:DomainName,Enabled:DistributionConfig.Enabled,OriginCount:DistributionConfig.Origins.Quantity,OriginDomain:DistributionConfig.Origins.Items[0].DomainName,DefaultOrigin:DistributionConfig.DefaultCacheBehavior.TargetOriginId,ExtraBehaviors:DistributionConfig.CacheBehaviors.Quantity}'
    )
    if (
        $distribution.Arn -ne 'arn:aws:cloudfront::291667884598:distribution/E2JZ8IOOSQ6MB9' -or
        $distribution.Status -ne 'Deployed' -or
        $distribution.Domain -ne 'd28yij2tl8eb0p.cloudfront.net' -or
        $distribution.Enabled -ne $true -or
        $distribution.OriginCount -ne 1 -or
        $distribution.OriginDomain -ne "$frontendBucket.s3.us-east-1.amazonaws.com" -or
        $distribution.DefaultOrigin -ne 'frontend-s3' -or
        $distribution.ExtraBehaviors -ne 0
    ) { throw 'CloudFront differs from the reviewed static-only setup.' }

    $protection = Invoke-FrontendAwsJson -AwsArguments @(
        's3api', 'get-public-access-block', '--bucket', $frontendBucket,
        '--expected-bucket-owner', '291667884598', '--query', 'PublicAccessBlockConfiguration'
    )
    foreach ($setting in @('BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets')) {
        if ($protection.$setting -ne $true) { throw "Bucket protection is not enabled: $setting" }
    }

    $ownership = Invoke-FrontendAwsJson -AwsArguments @(
        's3api', 'get-bucket-ownership-controls', '--bucket', $frontendBucket,
        '--expected-bucket-owner', '291667884598', '--query', 'OwnershipControls.Rules[0].ObjectOwnership'
    )
    if ($ownership -ne 'BucketOwnerEnforced') { throw 'Expected ACL-disabled bucket ownership.' }

    $encryption = Invoke-FrontendAwsJson -AwsArguments @(
        's3api', 'get-bucket-encryption', '--bucket', $frontendBucket,
        '--expected-bucket-owner', '291667884598', '--query', 'ServerSideEncryptionConfiguration.Rules[0].ApplyServerSideEncryptionByDefault.SSEAlgorithm'
    )
    if ($encryption -ne 'AES256') { throw 'Expected AES256 default bucket encryption.' }

    $before = Invoke-FrontendAwsJson -AwsArguments @(
        's3api', 'list-objects-v2', '--bucket', $frontendBucket,
        '--expected-bucket-owner', '291667884598', '--no-paginate'
    )
    if ($before.IsTruncated -eq $true -or ($null -ne $before.Contents -and @($before.Contents).Count -gt 0)) {
        throw 'The destination is no longer empty. Stop; do not overwrite or delete anything.'
    }

    Write-Host "Ready: 29 reviewed public website files -> $frontendBucket"
    if ((Read-Host 'Type PUBLISH STAGING to perform this real upload') -cne 'PUBLISH STAGING') {
        throw 'Cancelled before upload.'
    }

    $uploadedCount = 0
    try {
        foreach ($file in @($uploadFiles | Sort-Object Order, Key)) {
            $put = Invoke-FrontendAwsJson -AwsArguments @(
                's3api', 'put-object', '--bucket', $frontendBucket, '--key', $file.Key,
                '--body', $file.Path, '--expected-bucket-owner', '291667884598',
                '--if-none-match', '*', '--checksum-algorithm', 'SHA256',
                '--checksum-sha256', $file.Checksum, '--server-side-encryption', 'AES256',
                '--content-type', $file.ContentType, '--cache-control', $file.CacheControl
            )
            $uploadedCount += 1
            if ($put.ChecksumSHA256 -cne $file.Checksum -or $put.ServerSideEncryption -ne 'AES256') {
                throw "Upload response differs from expectations: $($file.Key)"
            }

            $head = Invoke-FrontendAwsJson -AwsArguments @(
                's3api', 'head-object', '--bucket', $frontendBucket, '--key', $file.Key,
                '--expected-bucket-owner', '291667884598', '--checksum-mode', 'ENABLED',
                '--query', '{Bytes:ContentLength,Checksum:ChecksumSHA256,ContentType:ContentType,CacheControl:CacheControl,Encryption:ServerSideEncryption}'
            )
            if (
                $head.Bytes -ne $file.Bytes -or $head.Checksum -cne $file.Checksum -or
                $head.ContentType -cne $file.ContentType -or $head.CacheControl -cne $file.CacheControl -or
                $head.Encryption -ne 'AES256'
            ) { throw "Stored object verification failed: $($file.Key)" }
            Write-Host "Uploaded and verified: $($file.Key)"
        }

        $after = Invoke-FrontendAwsJson -AwsArguments @(
            's3api', 'list-objects-v2', '--bucket', $frontendBucket,
            '--expected-bucket-owner', '291667884598', '--no-paginate'
        )
        if ($after.IsTruncated -eq $true -or @($after.Contents).Count -ne $uploadFiles.Count) {
            throw 'Final bucket inventory does not contain exactly the reviewed 29 objects.'
        }
        foreach ($file in $uploadFiles) {
            $stored = @($after.Contents | Where-Object { $_.Key -ceq $file.Key })
            if ($stored.Count -ne 1 -or $stored[0].Size -ne $file.Bytes) {
                throw "Final inventory mismatch: $($file.Key)"
            }
        }
        Write-Host 'PASS: 29 reviewed website objects uploaded and verified. Runtime services were not started.'
    }
    catch {
        Write-Host "STOP: $uploadedCount uploads returned success; the last request may need inspection. Preserve the objects and paste the error. Do not restart this block."
        throw
    }
}
```

## 3. Repeatable read-only HTML checks

Both routes passed on 17 October 2026. This block can be rerun to check
static HTML delivery only; it does not upload, sign in, or call the API.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    foreach ($url in @(
        'https://d28yij2tl8eb0p.cloudfront.net/'
        'https://d28yij2tl8eb0p.cloudfront.net/auth/callback.html'
    )) {
        $page = Invoke-WebRequest -UseBasicParsing -Uri $url -MaximumRedirection 0 -TimeoutSec 30
        if ($page.StatusCode -ne 200 -or $page.Headers['Content-Type'] -notlike 'text/html*') {
            throw "Expected HTTP 200 HTML: $url"
        }
        Write-Host "PASS: HTTP 200 HTML - $url"
    }
}
```

These HTTP checks alone do not establish browser behavior. The separate
read-only rendering check above adds limited CSS/layout and callback
JavaScript evidence, not Cognito-to-application membership, API connectivity,
or AI functionality. Those remain separate checks. The displayed dashboard's
operational/demo labels are not backend health evidence.

## 4. Stop conditions and recovery

- For expired credentials before upload, run `aws login --profile securecloudops-dev`
  and repeat only if no upload was attempted. For `AccessDenied`, paste the
  error; do not add broad permissions or change bucket public access.
- If an upload fails, times out, or reports an existing key, stop. It may
  have partially succeeded. Preserve objects for key-by-key inspection;
  do not rerun the empty-bucket block, remove `--if-none-match`, or delete
  objects as an automatic rollback. Bucket versioning/overwrite rollback
  is not established by this first publication.
- If the HTML requests fail after successful uploads, do not upload again.
  CloudFront can temporarily cache an earlier error; the default error-cache
  duration is ten seconds. A persistent failure may instead be a real
  permission/origin issue. Paste the status/error for diagnosis. See
  [AWS error caching](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/custom-error-pages-expiration.html).
  A query-string cache buster is not reliable with this distribution's
  cache policy. No invalidation is authorized or performed by these blocks.
- Keep runtime off, queue disabled, and the API connection disabled. Do not
  test sign-in, uploads of knowledge documents, or questions as part of this
  static-only checkpoint. Do not run Terraform apply to publish site files.

This procedure is intentionally specific to the reviewed, initially empty
bucket and fingerprint. Future website updates need a separate overwrite,
retention, and cache-refresh review.
