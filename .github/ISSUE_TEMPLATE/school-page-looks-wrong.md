---
name: A school page says something wrong
about: You know a California school and a number on its page does not match what you know
title: "[data] <school name or CDS code>: <what looks wrong>"
labels: ["bug"]
---

<!--
You do not need to know anything about this codebase to file this. If you work
at a California school or district, or you are a parent at one, you know things
about that school that no dataset check can see.

Homeroom joins California Department of Education extracts into school pages.
Every figure on a page comes from a state file named in PROVENANCE.md - this
project publishes no figure of its own. So a wrong number is one of three
things, and telling them apart is the useful part:

  1. the state published something wrong,
  2. Homeroom read the state's file wrong, or
  3. the page is right and it is being read in a way the page invites.

All three are worth filing. The third is the one this project is worst at
seeing from the inside.
-->

## Which page

- **URL:**
- **School name and CDS code (if you know it):**
- **Language of the page you were reading:** <!-- en / es -->

## What it says, and what you expected

- **The page says:** <!-- quote the figure and the label beside it -->
- **You expected:**
- **How you know:** <!-- "I am the registrar", "the district's own dashboard says otherwise", "I counted" - all fine. A guess is fine too, if you say it is one. -->

## Which of these is it, if you can tell

- [ ] The number is wrong
- [ ] The number may be right, but the label around it made me read it as something else
- [ ] The page shows a number where the state withheld one, or the other way round
- [ ] Something that should be on the page is missing
- [ ] I do not know which

<!--
The third box is the serious one. This project's rule is that a suppressed or
masked measure renders as "not published", never as zero and never guessed at,
and that "not reported" and "reported as zero" stay visibly different facts. If
a page blurred those two for you, that is a defect in the thing this project
exists to get right, and it is worth filing even if you are not sure.
-->

## Anything else

<!-- Screenshots are welcome. Nothing about an individual student, please - the
state masks small cells for a reason and so does this project. -->
