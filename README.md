# kai-poster (private)

GitHub Actions posts the next Kai Short to YouTube Shorts and Instagram Reels at 09:00 and 21:00 IST. It does a fresh upload each time, at most `MAX_PER_DAY` per day.

- **Queue:** `queue/NNN_EP.json` holds the metadata, and the matching `NNN_EP.mp4` is attached to the `queue` release.
- **Add episodes:** run `python -X utf8 enqueue.py <episode-folder> ...`.
- **Settings:**
  - Repo variables: `MAX_PER_DAY`, and `YT_PRIVACY` (`private` until the YouTube API audit passes).
  - Secrets: `YT_TOKEN_JSON` and `IG_TOKEN`. The Instagram token is refreshed weekly from Vijay's PC by `ig_refresh.py`.
- **Run now:** Actions → Post Kai Short → Run workflow.
