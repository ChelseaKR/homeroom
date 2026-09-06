"""The site origin: the template, the publish path, and the record of both.

`deploy/site/` is prepared and not applied, which is a state a directory can
drift out of in two directions. It can drift toward a template that would
deploy green and serve the site wrongly -- which is what
`tests/test_deploy_template.py` was written for, over the ask stack, and every
check there names a symptom that reached a reader. And it can drift toward a
document that says "nothing is applied" after something is, which is the
failure the comment above `DOCS_DESCRIBING_THE_SURFACE` in
`tests/test_published_site.py` records: four documents denied a running service
for a week, two of them edited during that week without the denial being
noticed.

So this file checks three artifacts against each other and against the
published tree: `deploy/site/template.yaml`, `.github/workflows/site-publish.yml`,
and `deploy/site/README.md`.

The template is read as text rather than parsed, for the reason
`tests/test_deploy_template.py` gives: CloudFormation YAML carries `!Ref`,
`!Sub` and `!GetAtt` tags that a plain YAML loader rejects, and adding a parser
plus a tag-tolerant loader to a stdlib-only project to check one file is the
worse trade. The block helpers below are that file's, deliberately re-stated
rather than imported: these are two separate deployment artifacts, and a shared
helper would make a change to one able to quietly narrow the checks on the
other.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "deploy" / "site" / "template.yaml"
RECORD = ROOT / "deploy" / "site" / "README.md"
WORKFLOW = ROOT / ".github" / "workflows" / "site-publish.yml"
PAGES_WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"
SITE = ROOT / "site"


def block(name: str) -> str:
    """One top-level entry of `Parameters:` or `Resources:`, by its indentation.

    A comment line sitting at the same two-space indent ends the block, which is
    what separates one resource's trailing prose from the next resource's body.
    """
    lines = TEMPLATE.read_text(encoding="utf-8").splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.startswith(f"  {name}:")), None
    )
    assert start is not None, f"no `{name}:` entry in the template"
    body = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith("    "):
            break
        body.append(line)
    return "\n".join(body)


def uncommented(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    )


@lru_cache(maxsize=1)
def template_source() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def record_source() -> str:
    return RECORD.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def workflow_source() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------------
# The template: the things a green `cloudformation deploy` still gets wrong.
# ----------------------------------------------------------------------------------


def test_the_origin_bucket_is_private_and_carries_no_acls() -> None:
    """A public bucket makes the distribution decorative and the OAC a no-op."""
    bucket = uncommented(block("SiteBucket"))
    for setting in (
        "BlockPublicAcls: true",
        "BlockPublicPolicy: true",
        "IgnorePublicAcls: true",
        "RestrictPublicBuckets: true",
    ):
        assert setting in bucket, setting
    assert "ObjectOwnership: BucketOwnerEnforced" in bucket, (
        "without BucketOwnerEnforced the bucket still has ACLs, which is a second "
        "way to make an object public that the four settings above do not cover"
    )


def test_the_origin_bucket_survives_deleting_the_stack() -> None:
    """`delete-stack` in the wrong terminal must not be able to take the site."""
    bucket = block("SiteBucket")
    assert "DeletionPolicy: Retain" in bucket
    assert "UpdateReplacePolicy: Retain" in bucket


def test_the_origin_uses_access_control_and_not_the_legacy_identity() -> None:
    """OAC, not OAI. OAI cannot be narrowed to one distribution ARN."""
    source = uncommented(template_source())
    assert "AWS::CloudFront::OriginAccessControl" in source
    assert "OriginAccessControlId:" in source
    assert "CloudFrontOriginAccessIdentity" not in source, (
        "the legacy Origin Access Identity is back in the template"
    )
    # An S3 origin under OAC must still declare S3OriginConfig, with the OAI
    # field explicitly empty. Dropping the line makes CloudFront treat the
    # bucket as a custom origin and every request 403s.
    assert 'OriginAccessIdentity: ""' in uncommented(block("Distribution"))


def test_the_origin_is_the_regional_bucket_name() -> None:
    """The global form redirects for a bucket outside us-east-1.

    A SigV4-signed origin request does not survive a redirect, so the symptom
    is a distribution that 301s or 400s for every object while the bucket, the
    policy and the OAC are all correct.
    """
    assert "!GetAtt SiteBucket.RegionalDomainName" in uncommented(block("Distribution"))


def test_http_is_redirected_and_the_tls_floor_is_modern() -> None:
    distribution = uncommented(block("Distribution"))
    assert "ViewerProtocolPolicy: redirect-to-https" in distribution
    assert "MinimumProtocolVersion: TLSv1.2_2021" in distribution


def test_the_default_root_object_is_the_landing_page() -> None:
    """`/` has to serve index.html: the sentinel compares the root against it."""
    assert "DefaultRootObject: index.html" in uncommented(block("Distribution"))


def test_a_missing_page_is_never_answered_with_a_two_hundred() -> None:
    """The single most common thing done to a static site behind a CDN.

    Mapping 403 or 404 to a 200 with a fallback page turns every request for a
    school that is not published into a success carrying some other page's
    bytes -- handed to a crawler as well as to a reader -- and it makes
    `tools/verify_live_site.py` vacuous: that file refuses to pass against an
    origin answering a guaranteed-missing path with anything but 404.
    """
    distribution = uncommented(block("Distribution"))
    assert "CustomErrorResponses:" in distribution
    assert "ErrorCode: 404" in distribution
    assert "ResponseCode:" not in distribution, (
        "a CustomErrorResponse now rewrites the status a missing page returns"
    )
    assert "ResponsePagePath:" not in distribution


def test_the_bucket_policy_lists_so_a_missing_key_is_a_404_and_not_a_403() -> None:
    """Without `s3:ListBucket` the live sentinel cannot run at all.

    S3 answers a GET for a key that does not exist with 403 AccessDenied rather
    than 404 NoSuchKey when the caller may not list the bucket -- it will not
    confirm absence -- and CloudFront passes the 403 through. Every real page
    would be correct and `prove_the_origin_discriminates` would exit 4 saying
    the origin cannot discriminate. CloudFront never issues a ListBucket
    request; this grant changes which of two error codes S3 returns.
    """
    policy = uncommented(block("SiteBucketPolicy"))
    assert "Action: s3:ListBucket" in policy
    assert "Action: s3:GetObject" in policy


def test_the_bucket_is_readable_by_this_distribution_and_no_other() -> None:
    """The service principal alone grants every CloudFront distribution on AWS."""
    policy = uncommented(block("SiteBucketPolicy"))
    assert policy.count("Service: cloudfront.amazonaws.com") == 2
    assert policy.count("AWS:SourceArn:") == 2, (
        "a cloudfront.amazonaws.com grant without an AWS:SourceArn condition lets "
        "any distribution in any AWS account read this bucket"
    )
    assert "aws:SecureTransport: false" in policy


def test_the_certificate_parameter_refuses_every_region_but_us_east_1() -> None:
    """CloudFront reads ACM certificates from us-east-1 and nowhere else.

    A certificate issued in the stack's own region is a valid certificate that
    CloudFront cannot see, and the deploy fails talking about the ARN rather
    than about regions. The pattern is what makes this checked instead of
    remembered.
    """
    declaration = uncommented(block("CertificateArn"))
    pattern = re.search(r"AllowedPattern:\s*\"(.+)\"", declaration)
    assert pattern, declaration
    expression = pattern.group(1)
    assert "acm:us-east-1:" in expression, expression
    for wrong in ("arn:aws:acm:us-west-2:012345678901:certificate/" + "a" * 36,):
        assert not re.fullmatch(expression, wrong), wrong
    assert re.fullmatch(
        expression, "arn:aws:acm:us-east-1:012345678901:certificate/" + "0" * 36
    )
    assert re.fullmatch(expression, ""), (
        "phase one deploys with no certificate at all, so the empty value has to pass"
    )


def test_both_documents_say_the_certificate_must_be_in_us_east_1() -> None:
    """A pattern that refuses an ARN explains nothing to whoever hit it."""
    assert "us-east-1" in template_source()
    assert "CloudFront reads ACM certificates only" in template_source()
    assert "us-east-1" in record_source()


def test_the_domain_is_not_hardcoded_in_the_template() -> None:
    """A template that names one site is a template that works for one site.

    The comments may name the domain and do -- the header states what is
    serving it today and where DNS points -- but no value in the template may,
    which is what `SiteDomain` is for.
    """
    domain = (SITE / "CNAME").read_text(encoding="utf-8").strip()
    assert domain, "site/CNAME names no domain"
    assert domain not in uncommented(template_source()), (
        f"{domain} is hardcoded in the template; it is the SiteDomain parameter"
    )
    assert "  SiteDomain:" in template_source()


def test_the_publish_role_is_pinned_to_one_repository_and_one_branch() -> None:
    """An unpinned `sub` lets every repository on GitHub assume this role.

    That is the classic GitHub-OIDC mistake and it is invisible once deployed:
    the role works, and it also works for strangers. Pinning it to the branch
    ci gates is also what stops a pull request from a fork publishing.
    """
    role = uncommented(block("PublishRole"))
    assert "token.actions.githubusercontent.com:sub" in role
    assert "repo:${GitHubRepository}:ref:refs/heads/${GitHubBranch}" in role
    assert "token.actions.githubusercontent.com:aud: sts.amazonaws.com" in role
    assert (
        "*"
        not in role.split("token.actions.githubusercontent.com:sub")[1].split("\n")[0]
    ), "the sub condition carries a wildcard"


def test_the_publish_role_grants_nothing_on_a_wildcard_resource() -> None:
    """`cloudfront:CreateInvalidation` on `*` is how that grant is usually written."""
    role = uncommented(block("PublishRole"))
    resources = [line.strip() for line in role.splitlines() if "Resource:" in line]
    assert resources, role
    for line in resources:
        assert '"*"' not in line and "'*'" not in line, line
    assert "distribution/${Distribution}" in role
    assert "!GetAtt SiteBucket.Arn" in role
    assert "${SiteBucket.Arn}/*" in role


def test_the_distribution_keeps_no_access_log() -> None:
    """A viewer IP beside a school page's path is a record about a family.

    GitHub Pages gives the owner no access log either, so leaving this off is
    what keeps the move invisible in the one way that matters. Turning it on is
    a change to docs/RESPONSIBLE-TECH-AUDITS.md before it is a change here.
    """
    assert "Logging:" not in uncommented(block("Distribution"))


def test_the_cache_key_is_the_path_alone() -> None:
    """Anything in the key multiplies the cache and can leak one reader's request."""
    policy = uncommented(block("CachePolicy"))
    assert "CookieBehavior: none" in policy
    assert "HeaderBehavior: none" in policy
    assert "QueryStringBehavior: none" in policy


# ----------------------------------------------------------------------------------
# The publish path: the bytes committed have to be the bytes served.
# ----------------------------------------------------------------------------------

ACTION_PIN = re.compile(r"uses:\s*([^@\s]+)@([^\s]+)")


def sync_passes() -> list[str]:
    """Each `aws s3 sync` command, with its backslash continuations joined."""
    joined = re.sub(r"\\\n\s*", " ", workflow_source())
    return [
        line.strip()
        for line in joined.splitlines()
        if line.strip().startswith("aws s3 sync")
    ]


@lru_cache(maxsize=1)
def published_kinds() -> frozenset[str]:
    """Every kind of file the published tree holds: an extension, or a filename.

    Derived from `site/` rather than listed here, so a page type that arrives
    with a new extension fails this file instead of being served as
    `binary/octet-stream` by a sync pass nobody added.
    """
    return frozenset(
        path.suffix or path.name for path in SITE.rglob("*") if path.is_file()
    )


def test_the_published_tree_holds_the_five_kinds_this_file_reasons_about() -> None:
    """The floor: if the tree stops holding these, every check below narrows."""
    assert published_kinds() == {".html", ".png", ".xml", ".txt", "CNAME"}


def test_every_action_the_publish_workflow_uses_is_pinned_to_a_full_sha() -> None:
    pins = ACTION_PIN.findall(workflow_source())
    assert pins, "the publish workflow uses no action at all"
    for action, ref in pins:
        assert re.fullmatch(r"[0-9a-f]{40}", ref), (action, ref)


def test_every_kind_of_published_file_is_synced_with_its_own_content_type() -> None:
    """`CNAME` has no extension, and the CLI's guess for it is a download.

    Four of the five kinds the site publishes are typed correctly by the
    extension alone. The fifth is `CNAME`, which the AWS CLI gives
    `binary/octet-stream`: a browser asked for it offers to save it. The site
    has published it since the first deploy and the sentinel compares it, so it
    is served, not incidental.
    """
    typed: dict[str, str] = {}
    for command in sync_passes():
        include = re.search(r"--include '([^']+)'", command)
        content_type = re.search(r"--content-type '([^']+)'", command)
        if include is None:
            continue
        assert content_type is not None, (
            f"this pass names a kind of file and no Content-Type: {command}"
        )
        typed[include.group(1)] = content_type.group(1)

    for kind in sorted(published_kinds()):
        pattern = f"*{kind}" if kind.startswith(".") else kind
        assert pattern in typed, (
            f"the site publishes {kind} files and no sync pass states their "
            f"Content-Type; the passes cover {sorted(typed)}"
        )
        assert "octet-stream" not in typed[pattern], (kind, typed[pattern])
    assert typed["CNAME"].startswith("text/plain"), typed["CNAME"]


def test_every_sync_pass_deletes_what_the_checkout_no_longer_publishes() -> None:
    """A page removed from `site/` has to stop being served.

    Without `--delete` a closed school's page, or an ask page a rollback
    removed, keeps answering 200 with numbers this repository no longer stands
    behind -- and every gate stays green, because every gate reads the checkout.
    """
    passes = sync_passes()
    assert len(passes) >= 6, passes
    for command in passes:
        assert "--delete" in command, command


def test_a_pass_sweeps_the_kinds_the_site_does_not_publish() -> None:
    """The typed passes cannot delete an object of a kind none of them matches."""
    sweeps = [c for c in sync_passes() if "--include" not in c]
    assert len(sweeps) == 1, sweeps
    for kind in sorted(published_kinds()):
        pattern = f"*{kind}" if kind.startswith(".") else kind
        assert f"--exclude '{pattern}'" in sweeps[0], (kind, sweeps[0])


def test_the_publish_proves_the_bucket_holds_what_the_checkout_publishes() -> None:
    """Filter semantics are an argument; a diff of the two inventories is a proof."""
    source = workflow_source()
    assert "list-objects-v2" in source
    assert "find . -type f" in source
    assert "diff -u /tmp/in-the-checkout.txt /tmp/in-the-bucket.txt" in source


def test_the_publish_reads_the_content_types_back_from_the_bucket() -> None:
    assert "head-object" in workflow_source()
    assert "--query ContentType" in workflow_source()


def test_a_republish_invalidates_the_whole_distribution_and_waits() -> None:
    """`/*` is one invalidation path; the 23,310 real ones would be $111 a publish."""
    source = workflow_source()
    assert "create-invalidation" in source
    assert "--paths '/*'" in source
    assert "wait invalidation-completed" in source, (
        "without the wait, the live sentinel can read an edge that has not turned "
        "over and report a difference that is not there"
    )


def test_the_publish_job_is_inert_until_the_owner_sets_the_variables() -> None:
    """This is what makes "nothing is applied" true of the workflow as well.

    With any one of the four unset the job is skipped, so merging the file
    creates nothing and cannot fail. Setting them is a step in the cutover.
    """
    source = workflow_source()
    condition = source[source.index("    if: >-") : source.index("runs-on:")]
    for variable in (
        "SITE_S3_BUCKET",
        "SITE_CLOUDFRONT_DISTRIBUTION_ID",
        "SITE_PUBLISH_ROLE_ARN",
        "SITE_AWS_REGION",
    ):
        assert f"vars.{variable} != ''" in condition, variable


def test_the_publish_workflow_holds_only_what_oidc_and_a_checkout_need() -> None:
    """Read as a block, not as a slice: a job's grants end where the indent does."""
    lines = workflow_source().splitlines()
    assert "permissions: {}" in lines, "the root grant is not `permissions: {}`"
    start = lines.index("    permissions:")
    granted = set()
    for line in lines[start + 1 :]:
        if not line.startswith("      "):
            break
        granted.add(line.strip())
    assert granted == {"contents: read", "id-token: write"}, granted


def test_the_publish_workflow_uses_no_stored_aws_key() -> None:
    """OIDC or nothing. A long-lived key in this repository's secrets would be
    a credential with no expiry standing behind 23,310 pages."""
    source = workflow_source()
    assert "AWS_ACCESS_KEY_ID" not in source
    assert "AWS_SECRET_ACCESS_KEY" not in source
    assert "role-to-assume:" in source


def test_the_publish_workflow_publishes_the_commit_ci_verified() -> None:
    """workflow_run checks out the default branch's tip, not the verified commit."""
    assert "github.event.workflow_run.head_sha || github.ref" in workflow_source()
    assert "persist-credentials: false" in workflow_source()


# ----------------------------------------------------------------------------------
# The record, held to the surface rather than trusted about it.
#
# `tests/test_published_site.py` derives whether the ask service is deployed from
# the published bytes and holds six documents to it, after four of them spent a
# week denying a running service. This is the same check pointed the other way:
# `deploy/site/README.md` says nothing is applied, and the thing that could make
# that a lie is somebody applying it and editing around the claim.
# ----------------------------------------------------------------------------------

# What an applied record carries and a prepared one cannot: the identifiers that
# only exist once AWS has created something. `deploy/ask/README.md` is the shape
# being contrasted with -- it carries a stack ARN, a Function URL and an account
# id in its first table.
APPLIED_IDENTIFIERS = {
    "a CloudFront distribution id": re.compile(r"\bE[A-Z0-9]{12,13}\b"),
    "a CloudFront distribution hostname": re.compile(
        r"\b[a-z0-9]{12,14}\.cloudfront\.net\b"
    ),
    "a CloudFormation stack ARN": re.compile(
        r"arn:aws:cloudformation:[a-z0-9-]+:\d{12}:"
    ),
    "an ACM certificate ARN": re.compile(r"arn:aws:acm:[a-z0-9-]+:\d{12}:certificate/"),
    "an IAM role ARN": re.compile(r"arn:aws:iam::\d{12}:role/"),
    "a named origin bucket": re.compile(r"homeroom-site-\d{12}"),
}


def test_the_site_record_claims_nothing_is_applied_and_carries_no_proof_of_one() -> (
    None
):
    """Both halves, because either alone can drift into a false document.

    The prose has to say it, so a reader is told; and the record has to be free
    of the identifiers an applied stack would put in it, so the prose cannot be
    left standing over a deploy that happened. If this stack is ever applied,
    this test fails first and the record gets rewritten the way
    `deploy/ask/README.md` was -- with the stack, the region, the ARN and the
    parameters as applied.
    """
    record = record_source()
    assert "Nothing here has been applied." in record
    assert "## What is NOT applied" in record
    for what, pattern in APPLIED_IDENTIFIERS.items():
        found = pattern.search(record)
        assert found is None, (
            f"deploy/site/README.md says nothing is applied and carries {what}: "
            f"{found.group(0)!r}. If it was applied, rewrite the record."
        )


def test_the_record_may_only_say_pages_is_the_live_deploy_while_pages_yml_is() -> None:
    """The claim is derived from the workflow that would have to change first.

    Cutting over means DNS, and DNS is not in this repository -- but leaving
    `pages.yml` publishing is what makes the rollback a single record, and the
    record says so. If somebody removes or disables that workflow, this fails
    and the document has to be re-argued rather than quietly becoming wrong.
    """
    pages = PAGES_WORKFLOW.read_text(encoding="utf-8")
    assert "actions/deploy-pages@" in pages
    assert "path: site" in pages
    record = record_source()
    assert "GitHub Pages serves every family reading these pages today" in record
    assert "pages.yml" in record


def test_the_record_and_the_workflow_name_the_same_repository_variables() -> None:
    """A cutover step that sets a variable nothing reads is a step that does nothing."""
    read_by_the_workflow = set(
        re.findall(r"vars\.([A-Z][A-Z0-9_]+)", workflow_source())
    )
    named_in_the_record = set(re.findall(r"\bSITE_[A-Z0-9_]+\b", record_source()))
    assert read_by_the_workflow == named_in_the_record, (
        read_by_the_workflow ^ named_in_the_record
    )
    assert len(read_by_the_workflow) == 4, sorted(read_by_the_workflow)


def test_the_record_names_the_domain_the_published_tree_names() -> None:
    domain = (SITE / "CNAME").read_text(encoding="utf-8").strip()
    assert domain in record_source()


@lru_cache(maxsize=1)
def published_measurements() -> tuple[int, int, int]:
    """Files, total bytes, and the largest single file, over the published tree."""
    sizes = [path.stat().st_size for path in SITE.rglob("*") if path.is_file()]
    return len(sizes), sum(sizes), max(sizes)


def test_the_records_measurements_are_the_published_trees_measurements() -> None:
    """The whole argument for moving hosts is arithmetic, so the arithmetic is held.

    `deploy/site/README.md` argues from the size of `site/`: what it costs on
    the new host, what the old cap left, what does not fit. A republish that
    changes the tree and not the document turns that argument into three stale
    numbers that still read as measurements. Re-measure and edit the document;
    never edit a number to fit.
    """
    files, total_bytes, largest = published_measurements()
    record = record_source()
    for value, what in (
        (files, "the published file count"),
        (total_bytes, "the published byte count"),
        (largest, "the largest published file"),
    ):
        assert f"{value:,}" in record, (
            f"deploy/site/README.md does not state {what}, {value:,}. Re-measure it."
        )


def test_the_record_states_the_file_count_that_ruled_cloudflare_pages_out() -> None:
    """20,000 files a deployment, and the site passed that before this was asked."""
    files, _, _ = published_measurements()
    assert files > 20000
    record = record_source()
    assert "20,000" in record
    assert "Cloudflare Pages was not an option" in record
