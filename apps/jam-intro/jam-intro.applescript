-- Jam Intro — launcher for the BUSY Bar animation, as a double-clickable app.
-- Built on the Mac with:
--   osacompile -o "$HOME/Jam Intro.app" jam-intro.applescript
-- Asks which effect to play, then runs the shell launcher in Terminal so the
-- usual checks (python3 present, bar answering) still apply.

set targetFolder to (POSIX path of (path to home folder)) & "Github/busybar-apps-dev/apps/jam-intro"
set effects to {"pool", "auto", "starfield", "plasma", "fire", "sparkle"}
set chosen to choose from list effects with title "Jam Intro" with prompt ¬
	"Quel effet sur la BUSY Bar ?" default items {"pool"} OK button name "Lancer" cancel button name "Annuler"

if chosen is false then return
set effectName to item 1 of chosen

tell application "Terminal"
	activate
	do script "cd " & quoted form of targetFolder & " && ./run-jam-intro.command run " & effectName
end tell
