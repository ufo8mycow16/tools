# Third Moon Audiobook Studio

Turns EPUB books (and pasted text or web pages) into full-cast audiobooks with Chatterbox Turbo, with Gemma
working out who says every line. Listen in the browser on the PC or the phone, or export a proper audiobook.

## Starting it
Double-click **START_AUDIOBOOK_STUDIO.bat**. It uses Chatterbox's own Python
(`C:\Users\Glen\ChatterboxTurbo\venv`), so there's nothing to install. The browser opens by itself.
On the phone (same Wi-Fi), open the address shown in the window, or on the Settings page, and "Add to Home screen".

Needs: Chatterbox Turbo (already installed), ffmpeg on the PATH (the Vulcan Fury voice scripts already use it),
and Ollama with `gemma4:12b` for the smart casting (optional - the rules work without her).

## How a book goes
1. **Library -> Add a book** (or drop EPUBs on the page). Front matter (copyright, contents, "also by") is left out.
2. **Gemma reads it** automatically: characters, who says each line, and how (angry, whispering...).
3. **Cast tab:** pick the narrator and a voice for each character. Voices come from
   `Documents\Vulcan Fury\Reference Voices`; Kirk, Spock, McCoy and friends are matched by name.
4. **Make the audio.** Runs in the background; chapters can be listened to as they finish. Only changed lines are
   ever remade.
5. **Listen** (read-along highlighting, 0.5x-4x, skip, bookmarks with notes, sleep timer, search, "story so far"),
   or **Export** a .m4b (chapters + cover) or MP3s for the car.

## Fixing things
- **Script tab:** every line with its speaker - click a speaker to change it, edit the spoken text, change the
  emotion, give one line its own voice, or redo just that line.
- **Pronunciation:** "written -> said as" for every book, or per book. Star Trek words are in there already.

## Where things are kept
Everything stays in this folder: `data\` (library database, settings), `library\` (book audio), `voices\` (voices
added in the app - Reference Voices is never written to), `exports\` (finished audiobooks).
