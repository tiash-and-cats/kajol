import shutil

try:
    from tqdm import tqdm
    
    def progress_bar(txt, progress, total):
        print("\r" + tqdm.format_meter(
            progress, total, 0, 
            prefix=txt, colour="cyan", 
            ncols=shutil.get_terminal_size().columns
        ), end="")
except ModuleNotFoundError:
    BLOCK = chr(9608)
    
    def progress_bar(txt, progress, total):
        """
        Based on Progress Bar Simulation, by Al Sweigart al@inventwithpython.com
        available at https://nostarch.com/big-book-small-python-programming
        """
        if len(txt) > 50:
            txt = txt[:47] + "..."

        bar = ''  # The progress bar will be a string value.
        bar += '['  # Create the left end of the progress bar.

        # Make sure that the amount of progress is between 0 and total:
        if progress > total:
            progress = total
        if progress < 0:
            progress = 0

        # Calculate the number of "bars" to display:
        bars = int((progress / total) * 30)

        bar += BLOCK * bars  # Add the progress bar.
        bar += ' ' * (30 - bars)  # Add empty space.
        bar += ']'  # Add the right end of the progress bar.

        # Calculate the percentage complete:
        pcent = round(progress / total * 100, 1)
        bar += ' ' + str(pcent).rjust(5) + '%'  # Add percentage.

        # Add the numbers:
        bar += ' ' + str(progress) + '/' + str(total)

        print("\r\x1b[2K" + txt.ljust(max(30, len(txt) + 5)) + bar, end="",
              flush=True)