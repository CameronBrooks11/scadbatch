# Support

## Where to ask

Open an issue: <https://github.com/CameronBrooks11/scadbatch/issues>

That is the only support channel. Bug reports, questions about how something is meant to work,
and requests all belong there, in the open, so the answer is findable by whoever asks next.

## What to expect

There is no guaranteed response time. This is maintained alongside other research work, so a
reply may take days or longer.

An issue that carries a reproduction gets answered first, because it can be acted on without a
round trip. That means:

- the `.scad` file, or a smaller one that shows the same thing
- the parameter file, small enough to paste
- the exact command you ran
- what you expected, and what happened
- the OpenSCAD version (`openscad --version`) — behaviour differs between releases

## Before filing

Check the [README](README.md) for the CSV and JSON rules: several things that look like bugs are
deliberate refusals, and the message usually names the file and line. If a run exits 0 but the
geometry is wrong, look at the `--summary` JSON — `counts.errors` reports errors OpenSCAD itself
exits 0 on.

Search the existing issues, including closed ones. A few known limits are recorded there with
measurements rather than fixed.

## Security

There is no private reporting channel configured. If you believe you have found a security
issue, open an issue describing the class of problem without a working exploit, and say that you
would rather discuss the details privately.
