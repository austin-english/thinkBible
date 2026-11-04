# AWS setup

How the ThinkBible AWS account is set up, how to sign in, and what's left to do. For daily
commands, see the **AWS** section of the [README](../README.md).

Real values (account IDs, portal URL, email) are kept out of this repo. They are in your password
manager and in `~/.aws/config`.

## The accounts

AWS's sign-up created a small **AWS Organization**. Accounts are free, and you only pay for what
runs in them.

| Account | What it's for | How you use it |
|---|---|---|
| **Management Account** | Billing, the budget, organization settings, and **IAM Identity Center** (your login) | Rarely: billing, or changing who can access what |
| **ThinkBible** | Everything the app runs on: Bedrock, S3, CloudFront, Terraform state | Daily |

There was a third account, *Identity Delegated Admin*, which AWS created to run Identity Center. It
was removed (deregistered, then closed). It shows as **Suspended** for 90 days, then disappears.
Identity Center is now managed from the Management Account.

## Signing in

| Login | Where | Use it for |
|---|---|---|
| **Everyday** | settings.aws.com, or the access portal URL (bookmarked). Then **ThinkBible** → **AdministratorAccess** | All normal work |
| **Root** (email + root password + root MFA) | console.aws.amazon.com → **Root user** | Emergencies only, e.g. if the everyday login breaks |

- Both logins use the same email, but they have **separate passwords**, each saved separately in
  the password manager.
- Inside ThinkBible you always act through a **role** (`AdministratorAccess`), never as root. The
  console's top-right menu shows the role name.
- Root has MFA (a passkey). Add a second, independent MFA device, such as an authenticator app, as
  a backup: sign in as root → account name → **Security credentials** → **Assign MFA device**.
- If you forget the everyday password, use **Forgot password** on the sign-in page.

## Terminal (AWS CLI with SSO)

The CLI uses short-lived credentials from IAM Identity Center. There are no access keys anywhere.

```bash
aws sso login --profile admin-thinkbible   # opens the browser; approve. Lasts up to 8 hours
export AWS_PROFILE=admin-thinkbible        # so the pipeline, Terraform and the CLI use it
aws sts get-caller-identity                # Arn should contain assumed-role/AWSReservedSSO_AdministratorAccess_…
```

`~/.aws/config` (created by `aws configure sso`):

```ini
[profile admin-thinkbible]
sso_session = thinkbible
sso_account_id = <ThinkBible account id>
sso_role_name = AdministratorAccess
region = us-west-2

[sso-session thinkbible]
sso_start_url = <access portal URL, IPv4-only>
sso_region = us-east-1
sso_registration_scopes = sso:account:access
```

### Regions (set by the organization's region policy)

AWS's setup attached a service control policy, `AdvancedModeRegionRestrictionSecurityControlPolicy`,
to the organization. It decides what each region may be used for. It applies even to
AdministratorAccess.

| Region | Allowed | ThinkBible uses it for |
|---|---|---|
| **us-west-2** (Oregon) | Everything | **Home region**: S3, Lambda, DynamoDB, Step Functions, Bedrock. Profile default |
| **us-east-1** (N. Virginia) | Only global services: IAM, CloudFront, ACM, Route 53, billing, login (`sso`), Bedrock invoke. **No S3 buckets, Lambda or DynamoDB** | IAM Identity Center (the login), CloudFront, and CloudFront's ACM certificate |
| **us-east-2** (Ohio) | Only Bedrock invoke and support tools | Nothing directly (cross-region inference may route here) |
| Any other region | Only Bedrock invoke | Nothing |

**This policy was edited on 2026-11-04.** AWS made Ohio the home region; we swapped Ohio and Oregon,
so the second statement is `UsEast2Partitional` on `us-east-2` (originally `UsWest2Partitional` on
`us-west-2`). To change it again: settings.aws.com → manage regions (opens the policy) → **Edit
policy** → paste → **Save**.
- Move or delete resources in a region **before** restricting it. Once restricted, you can't
  delete them there.
- Policies are limited to 5,120 characters, so paste the compact (no whitespace) JSON.

If a command fails with "explicit deny in a service control policy", you're in the wrong region
for that service.

### How the terminal access was set up (Management Account → IAM Identity Center, us-east-1)

1. **Settings → Management** tab → **Enable multi-account permissions**.
2. **Permission sets** → create `AdministratorAccess` (predefined, 8-hour sessions).
3. **AWS accounts** → **ThinkBible** → assign your user with `AdministratorAccess`.
4. On the Mac: `brew install awscli`, then `aws configure sso`:
   - start URL: the IPv4 portal URL;
   - SSO region: `us-east-1`;
   - account: ThinkBible, role: AdministratorAccess;
   - default region: `us-west-2`;
   - profile: `admin-thinkbible`.

To set this up on another machine, repeat step 4 only.

## Still to do

### Budget (Management Account)
Search **Budgets** → **Create budget** → **Monthly cost budget** template → $25, your email. Then
add alerts at 50%, 80% and 100%. Charges from every account are billed to the Management Account,
so this one budget covers everything.

### Bedrock model access (ThinkBible, us-west-2)
1. Open the ThinkBible console in **US West (Oregon)** → **Bedrock** → **Model catalog**.
2. Open **Claude Sonnet 5.5** → **Open in playground**. The first time, Anthropic asks for a
   one-time use-case form: "Batch summarisation of public-domain Bible commentaries (Matthew Henry,
   JFB, Adam Clarke) into study notes and questions for a Bible-reading app. No end-user chat."
   After that, all Claude models work.
3. Test with a real call, which costs a fraction of a cent:

   ```bash
   aws bedrock-runtime converse --model-id us.anthropic.claude-sonnet-5-5 \
     --messages '[{"role":"user","content":[{"text":"Reply with one word: hello"}]}]'
   ```

Model IDs available, as checked in us-east-2 on 2026-11-04. The `us.` profiles route across the US
regions:
- Inference profiles, which the pipeline uses: `us.anthropic.claude-sonnet-5-5`,
  `us.anthropic.claude-haiku-5-5`, `us.anthropic.claude-opus-5-5`. `global.…` versions also exist.
- Base model IDs: `anthropic.claude-sonnet-5-5`, `anthropic.claude-haiku-5-5`,
  `anthropic.claude-opus-5-5`.

## Done

- **Terraform state bucket**: `thinkbible-tfstate-<ThinkBible account id>` in **us-west-2**, with
  versioning on and all public access blocked. It was created by hand on 2026-11-04, after a first
  copy in us-east-2 was deleted. Put its name in the `infra/envs/dev` backend config. Every other
  bucket and CloudFront are created by Terraform.
- **Bucket naming**: `thinkbible-<purpose>[-<env>]-<ThinkBible account id>`, for example
  `thinkbible-sources-<id>` and `thinkbible-packs-dev-<id>`. Lowercase, hyphens, no dots.

## Later (not needed yet)

- **Prod account:** a new account in the organization (email `<you>+aws-prod@gmail.com`). Assign
  your user to it in Identity Center and add an `admin-thinkbible-prod` CLI profile.
- **Narrower daily access:** a `ThinkBibleDeveloper` permission set (Bedrock invoke, the ThinkBible
  buckets, CloudFront invalidation) to use instead of AdministratorAccess.
- **CI deploys:** a GitHub Actions role trusted through OIDC, created by Terraform. No stored keys.

## Troubleshooting

| Problem | Fix |
|---|---|
| CLI says the token or session expired | `aws sso login --profile admin-thinkbible` |
| `aws configure sso` says "No AWS accounts are available" | The permission set isn't assigned to ThinkBible: Management Account → IAM Identity Center → AWS accounts → ThinkBible → assign `AdministratorAccess` |
| IAM Identity Center says "not enabled" | Wrong region. Switch to **us-east-1**. Don't click Enable in a member account |
| "explicit deny in a service control policy" | Wrong region for that service (see **Regions**). Resources go in **us-west-2**, and CloudFront and its certificate in us-east-1 |
| `create-bucket` says "OperationAborted / conflicting conditional operation" | A bucket with that name was just deleted, and AWS can take minutes to an hour to free the name. Retry later |
| Everyday login is broken | Sign in as root (console.aws.amazon.com → Root user) and fix it from the Management Account |
