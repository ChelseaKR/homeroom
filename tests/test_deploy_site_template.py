"""The site origin: the template, the publish path, and the record of both.

`deploy/site/` was prepared and not applied until 2026-11-17, and has been
applied since, and either is a state a directory can drift out of in two
directions. It can drift toward a template that would deploy green and serve
the site wrongly -- which is what `tests/test_deploy_template.py` was written
for, over the ask stack, and every check there names a symptom that reached a
reader. And it can drift toward a document that does not say what is running,
which is the failure the comment above `DOCS_DESCRIBING_THE_SURFACE` in
`tests/test_published_site.py` records: four documents denied a running service
for a week, two of them edited during that week without the denial being
noticed. While this stack was only prepared, the record was held to saying
so; now it is held to saying what is applied, and to `deploy/site/served-by`.

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

from homeroom.missing import MISSING_PAGE_NAME
from homeroom.publish_limits import (
    SERVED_BY_CLOUDFRONT,
    SERVED_BY_FILE,
    read_served_by,
)

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


def error_responses(distribution: str) -> dict[int, str]:
    """Each `CustomErrorResponses` entry of the distribution, by its ErrorCode.

    Read by indentation, like `block`: an entry starts at `- ErrorCode: N` and
    runs to the next entry or to the first line indented less than the list.
    """
    lines = distribution.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.strip() == "CustomErrorResponses:"),
        None,
    )
    assert start is not None, "the distribution has no CustomErrorResponses"
    indent = len(lines[start]) - len(lines[start].lstrip())
    entries: dict[int, list[str]] = {}
    current: list[str] | None = None
    for line in lines[start + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        opening = re.match(r"\s*- ErrorCode: (\d+)\s*$", line)
        if opening:
            code = int(opening.group(1))
            assert code not in entries, f"two entries for ErrorCode {code}"
            current = entries.setdefault(code, [])
        elif current is not None:
            current.append(line.strip())
    return {code: "\n".join(body) for code, body in entries.items()}


def rewritten_statuses(distribution: str) -> dict[int, list[str]]:
    """Every entry that hands a reader a status other than the origin's own."""
    return {
        code: stated
        for code, body in error_responses(distribution).items()
        if (stated := re.findall(r"ResponseCode: (\S+)", body))
        and stated != [str(code)]
    }


def test_a_missing_address_answers_404_never_200() -> None:
    """The single most common thing done to a static site behind a CDN.

    Mapping 403 or 404 to a 200 with a fallback page turns every request for a
    school that is not published into a success carrying some other page's
    bytes -- handed to a crawler as well as to a reader -- and it makes
    `tools/verify_live_site.py` vacuous: that file refuses to pass against an
    origin answering a guaranteed-missing path with anything but 404.

    Until 2026-11-17 this was held by forbidding `ResponseCode` and
    `ResponsePagePath` outright, and the cost of that was the body: S3's XML
    error document, shown to a parent as a tree of tags. A missing address now
    answers with a page (`site/404.html`), so what is held is the thing that
    mattered all along. Wherever an entry states a status, it states the one
    the origin gave; no entry anywhere says 200; and the 404 entry says 404 in
    so many words, because an entry with a page and no `ResponseCode` is not
    deployable and one with any other number is the failure above.
    """
    distribution = uncommented(block("Distribution"))
    entries = error_responses(distribution)
    assert set(entries) == {403, 404}, sorted(entries)
    assert not rewritten_statuses(distribution), rewritten_statuses(distribution)
    assert "ResponseCode: 200" not in distribution
    assert "ResponseCode: 404" in entries[404].splitlines(), entries[404]


def test_control_a_status_rewritten_to_200_is_caught() -> None:
    """The check above has to notice the edit it exists to stop."""
    distribution = uncommented(block("Distribution"))
    for wrong in ("200", "403", "302"):
        sabotaged = distribution.replace("ResponseCode: 404", f"ResponseCode: {wrong}")
        assert sabotaged != distribution, wrong
        assert rewritten_statuses(sabotaged) == {404: [wrong]}, wrong
    # And a page hung on the 403 entry with a friendlier status is one too.
    dressed = distribution.replace(
        "- ErrorCode: 403\n",
        "- ErrorCode: 403\n            ResponseCode: 404\n",
        1,
    )
    assert dressed != distribution
    assert rewritten_statuses(dressed) == {403: ["404"]}


def test_a_missing_address_answers_with_the_page_the_tree_publishes() -> None:
    """The path the distribution names has to be a file `site/` carries.

    A `ResponsePagePath` naming an object that is not in the bucket is a
    custom error page that never arrives: the status stays right and the body
    goes back to an error document. The publish uploads `site/` and nothing
    else, so the name in the template is held to the name the renderer writes
    and to the committed file, and to being an `.html` file, which is the kind
    the publish gives `text/html`.
    """
    entries = error_responses(uncommented(block("Distribution")))
    paths = re.findall(r"ResponsePagePath: (\S+)", entries[404])
    assert paths == [f"/{MISSING_PAGE_NAME}"], paths
    assert (SITE / MISSING_PAGE_NAME).is_file(), (
        f"the distribution answers a missing address with /{MISSING_PAGE_NAME} "
        "and the published tree does not carry it"
    )
    assert MISSING_PAGE_NAME.endswith(".html")
    assert "--include '*.html'" in workflow_source()


def test_a_refused_read_is_not_dressed_as_a_missing_page() -> None:
    """403 keeps S3's own answer: no page, no status of its own.

    With `s3:ListBucket` granted, S3 answers 403 only when CloudFront may not
    read an object that exists -- a bucket policy or an Origin Access Control
    that stopped matching. Sending that to the missing page would show every
    family "page not found" for a school that is published, and would leave
    the sentinel's guaranteed-missing check passing through the outage.
    """
    forbidden = error_responses(uncommented(block("Distribution")))[403]
    assert "ResponseCode" not in forbidden, forbidden
    assert "ResponsePagePath" not in forbidden, forbidden


def test_an_error_is_cached_for_seconds_not_minutes() -> None:
    """CloudFront's default is 300 seconds, which outlives the publish that caused it."""
    for code, body in error_responses(uncommented(block("Distribution"))).items():
        ttl = re.findall(r"ErrorCachingMinTTL: (\d+)", body)
        assert len(ttl) == 1, (code, body)
        assert int(ttl[0]) <= 60, (code, ttl)


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
    assert SUBJECT_TEMPLATE in role
    assert "token.actions.githubusercontent.com:aud: sts.amazonaws.com" in role
    assert (
        "*"
        not in role.split("token.actions.githubusercontent.com:sub")[1].split("\n")[0]
    ), "the sub condition carries a wildcard"


# The subject the role is pinned to, as the template writes it, and the two
# repositories the checks below render it for. The ids are made up: the real
# ones are a parameter, and `test_the_subject_ids_are_a_parameter...` holds the
# template to that.
SUBJECT_TEMPLATE = "repo:${GitHubOidcSubjectRepository}:ref:refs/heads/${GitHubBranch}"
IMMUTABLE_REPOSITORY = "octo-org@1234567/a.site_repo@7654321"
MUTABLE_REPOSITORY = "octo-org/a.site_repo"


def subject_pattern() -> str:
    declaration = uncommented(block("GitHubOidcSubjectRepository"))
    pattern = re.search(r"AllowedPattern:\s*\"(.+)\"", declaration)
    assert pattern, declaration
    return pattern.group(1)


def trust_condition() -> str:
    """The role's trust policy alone: from its `Condition:` to its `Policies:`."""
    role = uncommented(block("PublishRole"))
    assert "Condition:" in role and "Policies:" in role, role
    return role.split("Condition:")[1].split("Policies:")[0]


def rendered_subject(repository: str, branch: str = "main") -> str:
    """What `!Sub` makes of the `sub` condition for one pair of parameters."""
    line = next(
        line
        for line in trust_condition().splitlines()
        if "token.actions.githubusercontent.com:sub" in line
    )
    written = re.search(r"!Sub \"(.+)\"", line)
    assert written, line
    subject = written.group(1)
    names = set(re.findall(r"\$\{([A-Za-z:]+)\}", subject))
    assert names == {"GitHubOidcSubjectRepository", "GitHubBranch"}, (
        f"the sub condition is built from {sorted(names)}; a third input is a "
        f"third thing that has to be right for the role to be assumable"
    )
    return subject.replace("${GitHubOidcSubjectRepository}", repository).replace(
        "${GitHubBranch}", branch
    )


def test_the_publish_role_trusts_the_subject_github_actually_issues() -> None:
    """The first publish failed on this, 2026-11-17, and uploaded nothing.

    The repository issues GitHub's immutable subject claims, which carry the
    owner's and the repository's numeric ids. The role's condition was written
    from `owner/name`, `StringEquals` compared the two, and STS answered "Not
    authorized to perform sts:AssumeRoleWithWebIdentity" twelve times. The
    stack had deployed green and every other check on the role passed, because
    a role nobody can assume looks exactly like a role that is correctly
    pinned.
    """
    assert rendered_subject(IMMUTABLE_REPOSITORY) == (
        "repo:octo-org@1234567/a.site_repo@7654321:ref:refs/heads/main"
    )


def test_the_mutable_owner_name_form_no_longer_satisfies_the_condition() -> None:
    """Both ways it could come back: through the template and through a parameter.

    `repo:owner/name:ref:refs/heads/main` is the subject the role used to be
    pinned to and the one GitHub does not issue here. The template must not
    build the condition from `GitHubRepository` any more, the condition it does
    build must not equal the mutable subject for an id-form repository, and
    the parameter must refuse `owner/name` outright -- so that leaving the ids
    out fails at the change set instead of creating a role that cannot be
    assumed.
    """
    mutable_subject = f"repo:{MUTABLE_REPOSITORY}:ref:refs/heads/main"
    condition = trust_condition()
    assert "${GitHubRepository}" not in condition, (
        "the trust policy is built from GitHubRepository again, which is the "
        "owner/name form GitHub does not issue for this repository"
    )
    assert rendered_subject(IMMUTABLE_REPOSITORY) != mutable_subject
    assert not re.fullmatch(subject_pattern(), MUTABLE_REPOSITORY), (
        "GitHubOidcSubjectRepository accepts owner/name, so the condition that "
        "failed on 2026-11-17 can be deployed again"
    )


def test_the_subject_parameter_accepts_the_id_form_and_nothing_wider() -> None:
    """A strict pattern, because this value is the whole of the role's trust.

    Each refused value is a way the subject could be widened or bent: a
    missing id on either half, a wildcard, and a `:` that would let one value
    carry a second claim segment (`...:ref:refs/heads/x`) into the condition.
    """
    expression = subject_pattern()
    assert re.fullmatch(expression, IMMUTABLE_REPOSITORY)
    assert re.fullmatch(expression, "ChelseaKR@1/homeroom@2")
    for wrong in (
        MUTABLE_REPOSITORY,
        "octo-org@1234567/a.site_repo",
        "octo-org/a.site_repo@7654321",
        "octo-org@/a.site_repo@7654321",
        "octo-org@1234567/a.site_repo@",
        "octo-org@abc/a.site_repo@7654321",
        "octo-org@1234567/*@7654321",
        "*@1234567/a.site_repo@7654321",
        "*",
        "octo-org@1234567/a.site_repo@7654321:ref:refs/heads/main",
        "octo-org@1234567/a.site_repo@7654321/extra@1",
        "repo:octo-org@1234567/a.site_repo@7654321",
        " octo-org@1234567/a.site_repo@7654321",
        "",
    ):
        assert not re.fullmatch(expression, wrong), wrong


def test_the_trust_policy_compares_the_subject_exactly() -> None:
    """`StringLike` on `sub` is where a wildcard gets in later, unnoticed.

    Both conditions sit under one `StringEquals`: the audience, so a token
    minted for some other service is refused, and the subject, so every
    repository and branch but one is.
    """
    condition = trust_condition()
    assert "StringEquals:" in condition
    assert "StringLike" not in condition
    assert "ForAnyValue" not in condition
    under_equals = condition.split("StringEquals:")[1]
    assert "token.actions.githubusercontent.com:aud: sts.amazonaws.com" in under_equals
    assert f'token.actions.githubusercontent.com:sub: !Sub "{SUBJECT_TEMPLATE}"' in (
        under_equals
    )


def test_the_subject_ids_are_a_parameter_with_no_default() -> None:
    """One repository's ids do not belong in a template anyone may deploy.

    And no default is also what makes forgetting the parameter an error at the
    change set, which is the cheap place to find out. The comments explain the
    form with placeholders; no line of the template, comment or not, carries
    an `owner@digits/name@digits` value.
    """
    declaration = uncommented(block("GitHubOidcSubjectRepository"))
    assert "Type: String" in declaration
    assert "Default:" not in declaration, declaration
    hardcoded = re.search(
        r"[A-Za-z0-9_.-]+@[0-9]+/[A-Za-z0-9_.-]+@[0-9]+", template_source()
    )
    assert hardcoded is None, (
        f"{hardcoded.group(0)!r} is written into the template; it is the "
        f"GitHubOidcSubjectRepository parameter"
    )


def test_the_record_and_the_commands_pass_the_subject_parameter() -> None:
    """A required parameter the documented commands omit is a failed deploy.

    Every parameter file the two documents show names `GitHubRepository`, and
    each of those must name the subject parameter beside it; and both must say
    where the value is read from, because composing it by hand from
    `owner/name` is the mistake.
    """
    for path in (RECORD, RECORD.parent / "CUTOVER.md"):
        text = path.read_text(encoding="utf-8")
        files = re.findall(r"^\[\n(?:  \{.*\},?\n)+\]$", text, re.M)
        assert files, f"{path.name} shows no parameter file"
        for shown in files:
            assert '"GitHubOidcSubjectRepository"' in shown, (
                f"{path.name} shows a parameter file without the subject:\n{shown}"
            )
        assert "actions/oidc/customization/sub" in text, (
            f"{path.name} does not say where the subject is read from"
        )


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


def test_the_published_tree_holds_the_six_kinds_this_file_reasons_about() -> None:
    """The floor: if the tree stops holding these, every check below narrows.

    `.js` joined on 2026-09-17: `analytics.js`, the Google Analytics loader
    `homeroom.analytics` writes at the site root. `.css` joins with the first
    republish after #98 (`homeroom.css`, the one shared stylesheet), and the
    publish workflow already has its pass, so the tree may hold it or not --
    and nothing else.
    """
    floor = {".html", ".png", ".xml", ".txt", ".js", "CNAME"}
    assert floor <= published_kinds() <= floor | {".css"}, published_kinds()


def test_every_action_the_publish_workflow_uses_is_pinned_to_a_full_sha() -> None:
    pins = ACTION_PIN.findall(workflow_source())
    assert pins, "the publish workflow uses no action at all"
    for action, ref in pins:
        assert re.fullmatch(r"[0-9a-f]{40}", ref), (action, ref)


def test_every_kind_of_published_file_is_synced_with_its_own_content_type() -> None:
    """`CNAME` has no extension, and the CLI's guess for it is a download.

    Five of the six kinds the site publishes are typed correctly by the
    extension alone. The sixth is `CNAME`, which the AWS CLI gives
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
# week denying a running service. This is the same check for the site's origin.
# Until 2026-11-17 `deploy/site/README.md` said nothing was applied, and this
# held it to carrying no identifier an applied stack would leave. The stack was
# applied that day and DNS moved, so the check turned over, as its docstring
# said it would: the record now has to say what is applied, and which origin
# it says serves the domain has to be the one `deploy/site/served-by` names.
# ----------------------------------------------------------------------------------

# What the record must not carry even now that it is an applied one: anything
# that holds the AWS account id. `deploy/ask/README.md` carried a stack ARN and
# the id itself until 2026-10-17. The template keeps the account out of the
# committed bytes with `${AWS::AccountId}`, `params.json` is ignored for the
# same reason, and a record that spelled the bucket's name or the role's ARN
# would undo both in one paragraph.
ACCOUNT_BEARING_IDENTIFIERS = {
    "a CloudFormation stack ARN": re.compile(
        r"arn:aws:cloudformation:[a-z0-9-]+:\d{12}:"
    ),
    "an ACM certificate ARN": re.compile(r"arn:aws:acm:[a-z0-9-]+:\d{12}:certificate/"),
    "an IAM role ARN": re.compile(r"arn:aws:iam::\d{12}:role/"),
    "a named origin bucket": re.compile(r"homeroom-site-\d{12}"),
    "a bare AWS account id": re.compile(r"(?<![\d,.@])\d{12}(?![\d,])"),
}

# What an applied record carries and a prepared one could not: the name AWS
# gave the distribution, which is also what the domain's DNS record points at.
DISTRIBUTION_HOSTNAME = re.compile(r"\b[a-z0-9]{12,14}\.cloudfront\.net\b")


def template_parameters() -> list[str]:
    """Every name declared under `Parameters:`, in the template's order."""
    lines = template_source().splitlines()
    start = lines.index("Parameters:")
    names = []
    for line in lines[start + 1 :]:
        if line and not line.startswith(" ") and not line.startswith("#"):
            break
        found = re.fullmatch(r"  ([A-Za-z][A-Za-z0-9]*):", line)
        if found:
            names.append(found.group(1))
    return names


def test_the_site_record_says_what_is_applied_and_which_origin_serves() -> None:
    """The record follows `deploy/site/served-by`, in both directions.

    While the switch says `cloudfront` the stack is what families are served
    from, and a record that still said "prepared" would be the document
    denying a running service that this file exists to prevent. So it has to
    say it is applied and give what an applied record gives: the stack, the
    region, the distribution's name, and every parameter as applied. If the
    switch is ever pointed back at `github-pages`, the record has to say the
    move was rolled back rather than go on describing CloudFront as the
    origin.
    """
    record = record_source()
    served_by = read_served_by(ROOT / SERVED_BY_FILE)
    assert "Nothing here has been applied" not in record
    if served_by != SERVED_BY_CLOUDFRONT:
        assert "rolled back" in record.lower(), (
            f"{SERVED_BY_FILE} says {served_by!r}; deploy/site/README.md has to "
            "say the move was rolled back and when"
        )
        return
    assert "**This is applied.**" in record
    assert "## As applied" in record
    assert "`homeroom-site`" in record
    assert "`us-west-2`" in record
    assert DISTRIBUTION_HOSTNAME.search(record), (
        "deploy/site/README.md says it is applied and does not name the "
        "distribution the domain points at"
    )
    parameters = template_parameters()
    assert len(parameters) >= 10, parameters
    for name in parameters:
        assert f"`{name}`" in record, (
            f"deploy/site/README.md does not state {name} as applied"
        )


MISSING_PAGE_PREPARED = "**The missing-page response is prepared and not applied.**"
MISSING_PAGE_APPLIED = re.compile(
    r"\*\*The missing-page response was applied on \d{4}-\d{2}-\d{2}\.\*\*"
)


def test_the_record_says_whether_the_missing_page_response_is_running() -> None:
    """One sentence or the other, never neither and never both.

    The template carries a custom error response that was written on
    2026-11-17 and applied by nobody that day. A template in this directory is
    read as what the stack is -- the record says so in its first line -- so the
    one part of it that is not yet running has to be named as such, and has to
    go on being named until somebody applies it and writes down when. This
    cannot check which is true; it can make the record say one of them, in the
    words that tell a reader which to go and verify, and keep the plan they
    need beside it.
    """
    record = record_source()
    prepared = MISSING_PAGE_PREPARED in record
    applied = MISSING_PAGE_APPLIED.search(record) is not None
    assert prepared != applied, (
        "deploy/site/README.md has to say either that the missing-page response "
        "is prepared and not applied, or the date it was applied -- exactly one"
    )
    assert "## Prepared, not applied: a page for a missing address" in record
    for needed in (
        "ResponseCode: 404",
        f"ResponsePagePath: /{MISSING_PAGE_NAME}",
        "UsePreviousValue=true",
        "`Replacement` `False`",
        "tools/verify_live_site.py",
    ):
        assert needed in record, needed
    # The plan in the record keeps every parameter, so it names every one.
    for name in template_parameters():
        assert f"ParameterKey={name},UsePreviousValue=true" in record, name


def test_the_site_record_carries_nothing_that_holds_the_account_id() -> None:
    """Applied is not a reason to print the account.

    The record names the stack, the region and the distribution. It does not
    name the bucket, whose name ends in the account id, or give any ARN, each
    of which carries it. Those are read from the stack's outputs when they are
    needed.
    """
    record = record_source()
    for what, pattern in ACCOUNT_BEARING_IDENTIFIERS.items():
        found = pattern.search(record)
        assert found is None, (
            f"deploy/site/README.md carries {what}: {found.group(0)!r}. Name "
            "the stack output it is read from instead."
        )


def test_the_record_may_only_call_pages_the_rollback_while_pages_yml_deploys() -> None:
    """The claim is derived from the workflow that would have to change first.

    The rollback is one DNS record because `pages.yml` keeps publishing every
    tree that fits, and the record says so. If somebody removes or disables
    that workflow, this fails and the document has to be re-argued rather than
    quietly becoming wrong about what a rollback would serve.
    """
    pages = PAGES_WORKFLOW.read_text(encoding="utf-8")
    assert "actions/deploy-pages@" in pages
    assert "path: site" in pages
    record = record_source()
    assert "GitHub Pages no longer serves families. It is the rollback copy" in record
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
