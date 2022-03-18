# Things to run on the Promethion tower (or the Minion box)

## `clean_upstream.sh`

`clean_upstream.sh` scans for runs in /data which have been tagged as OK to
delete by Hesiod, and offers to delete them. It's pretty much ready to
go.

## System tray icon

`pstray_try3.py` is my attempt to see if it's feasible to have a system tray
icon which shows whether data is being sysced in a timely manner. It seems
like it is. But I have to think some more on how this can be made to work
reliably...

How will I know what the status should be? Hesiod normally runs every 5 minutes.
I could make it touch a file every time it starts, but this only shows that it
started. Maybe there are errors.

I could make it touch a file every time it finishes. Furthermore this file could
have the number of runs that are in the error state, if any. Now there may be a delay
because the pipeline is busy, so I would give some leeway as follows...

1) If there are zero runs in error state, and the touch file is <15 minutes old,
   show a smiley face, and message says "Hesiod running OK"
2) If the file is >15 minutes old, or the number of errors is non-zero, show
   the concerned face, and the message says
   "Hesiod last ran {} minutes ago, reporting {} runs in error state."
3) If the file is >60 minutes old or missing, show the skull icon and say
   "Hesiod is not running"

As well as the status message, and the "Quit Hesiod Monitor" menu option,
show a summary of the cells which are finished. Clicking on this triggers the deletion
logic, which I'd want to re-code in Python. I should be able to use PyGtk to make
a dialog box here. May have to spawn a new process due to the event loop restrictions.
Or I could run the shell script but that is super-hacky!

So all this is deffo do-able. Question is do I want to spend the time. I can propose
this at some point. Sorting out the ability to list libraries in pools is surely the
higher priority.
