#!/usr/bin/env python3

"""xtract_attachment.py

   Utility to extract the attachment(s) from an "xml" file following the
       Italian "Fattura Elettronica" format.
   Can be used as a command line utility or imported as a module,
       to be used inside other python programs.
   NOTE: written and tested with Python 3.6.7

   Usage:
       ./xtract_attachment.py [-h] [-o OUTDIR] [-s {low,max}] path

       positional arguments:
           path                  A file or a folder to be parsed.

       optional arguments:
           -o OUTDIR, --outdir OUTDIR
                                Output directory
           -s {low,max}, --safety {low,max}
                                (default: "max") If file already exists:
                                    "max" == do *not* overwrite.
                                    "low" == overwrite

   Exceptions:
       This program has some `except Exception` statements that can be
           considered too broad, instead these are wanted as such to permit
           processing a large number of files without being stopped by an
           error with one of them.

   (c) 2019 Alessandro Labate
"""

import argparse
import base64
import os
import re
import sys


# Assign `True` to override argparse section and set `path = cwd`.
#+ Used to "compile" with pyinstaller.
_pyinstaller_trick = False # pylint: disable=invalid-name

regex = { # pylint: disable=invalid-name
    'allegati' : re.compile(r'''<\s*Allegati\s*>
                                (.*?)
                                <\s*/\s*Allegati\s*>''',
                            re.X | re.S), # NOTE: re.DOTALL
    'nome' : re.compile(r'''<\s*NomeAttachment\s*>
                            \s*(.{1,60}?)\s*
                            <\s*/\s*NomeAttachment\s*>''',
                        re.X),
    'algoritmo' : re.compile(r'''<\s*AlgoritmoCompressione\s*>
                                 \s*(.{1,10}?)\s*
                                 <\s*/\s*AlgoritmoCompressione\s*>''',
                             re.X),
    'formato' : re.compile(r'''<\s*FormatoAttachment\s*>
                               \s*(.{1,10}?)\s*
                               <\s*/\s*FormatoAttachment\s*>''',
                           re.X),
    'descrizione' : re.compile(r'''<\s*DescrizioneAttachment\s*>
                                (.{1,100}?)
                                <\s*/\s*DescrizioneAttachment\s*>''',
                               re.X),
    'allegato' : re.compile(r'''<\s*Attachment\s*>
                                ([a-zA-Z0-9+/=\s]*?)
                                <\s*/\s*Attachment\s*>''',
                            re.X) # NOTE: \s inside char set to match
                                  #+ multiline encoded attachments
    }


def yield_xml_files(path):
    """Open, read and yield "xml" file(s) content.

       NOTE: generator function.

       Parameters:
           path -- string, path to a file or a direcotry

       Returns:
           yield a tuple (path, xml)
               path -- string, absolute path to file
               xml -- string, the content of xml file
    """
    files = []
    path = os.path.abspath(path)

    try:
        files = (os.path.join(path, i) for i in os.listdir(path)
                 if os.path.isfile(os.path.join(path, i))
                 and i.endswith('.xml'))
    except NotADirectoryError:
        files = [path]
    except FileNotFoundError as ex:
        print(ex, file=sys.stderr)
        exit(1)

    for path_ in files:
        try:
            with open(path_, 'r') as file:
                yield (path_, file.read())
        except Exception as ex: # pylint: disable=broad-except
            print(ex, file=sys.stderr)


def list_attachments(file):
    """List all the <Allegati> tag(s) found in a given "file".

    Parameters:
        file -- tuple, (path, xml)
            path -- string, absolute path to file
            xml -- string, an already read xml file

    Returns:
        a list of tuples [(path, attachment), ...]
            path -- string, absolute path to file
            attachment -- string, the content of a single <Allegati> tag
        NOTE: if none is found, returns empty list.
    """
    attachments = []
    path, xml = file
    found = regex.get('allegati').findall(xml)
    if found:
        for allegato in found:
            attachments.append((path, allegato))

    return attachments


def yield_decoded_attachment(attachments):
    """Decode, name and yield an attachment.

    NOTE: generator function.

    - Parse a list of <Allegati> tag(s) to find and decode (base64)
        the actual attachment, contained in the <Attachment> tag.
    - Look for the <NomeAttachment> tag to name the file.
    - Guess filetype or look for the <FormatoAttachemnt> tag.

    Parameters:
        attachments -- list of tuples, [(path, attachment), ...]
            path -- string, absolute path to file
            attachment -- string, the content of a single <Allegati> tag

    Returns:
        yields a tuple (filename, attachment)
            dirname -- string, directory part of the path
            filename -- string, basename for the attachment
            attachment -- bytes, decoded <Attachment> tag
    """
    for idx, (path, attachment) in enumerate(attachments):

        attachment_ = regex.get('allegato').search(attachment)
        dirname, basename = os.path.split(path)
        # Parse <NomeAttachment> tag
        nome = regex.get('nome').search(attachment)
        try:
            # Even being a mandatory TAG, I prefer to have a fallback
            nome = nome.group(1)
        except Exception: # pylint: disable=broad-except
            basename_ = os.path.splitext(basename)[0]
            nome = f'{basename_}_allegato_{idx+1}'
        # Parse <Attachment> tag
        try:
            attachment_ = attachment_.group(1)
            attachment_ = base64.b64decode(attachment_)
        except Exception as ex: # pylint: disable=broad-except
            # No <Attachment> tag or fail to decode
            print(f'Error decoding "{nome}" in "{basename}" : {ex}',
                  file=sys.stderr)
            continue
        # Check for empty attachment
        if attachment_ == b'':
            continue
        # Attempt to determine file type and set extension
        if attachment_[:5] == b'%PDF-':
            ext = 'pdf'
        # Add other possible file type checks here `elif`...
        elif regex.get('formato').search(attachment):
            ext = regex.get('formato').search(attachment)
            ext = ext.group(1).lower()
        else:
            ext = 'formatoSconosciuto'

        yield (dirname, f'{nome}.{ext}', attachment_)


def write_attachment(attachment, outdir=None, safety='max'):
    """Write an "attachment" to file.

       Parameters:
           attachment -- tuple, (dirname, filename, attachment)
               dirname -- string, the dir part of path
               filename -- string, filename with extension
               attachment -- bytes, decoded <Attachment> tag
           outdir -- string, a user provided directory for output
           safety -- string, what to do if a file exists?
               max : do *not* overwrite
               low : overwrite

       Returns:
           nothing, just writes to a file.
    """
    dirname, filename, attachment = attachment
    if outdir:
        outpath = os.path.join(outdir, filename)
    else:
        outpath = os.path.join(dirname, filename)
    # Actually anything other than 'low' is 'max'
    mode = 'wb' if safety == 'low' else 'xb'
    try:
        with open(outpath, mode) as file:
            file.write(attachment)
    except Exception as ex: # pylint: disable=broad-except
        print(ex, file=sys.stderr)


def main():
    """main()"""
    if _pyinstaller_trick:
        # Override argparse
        path = '.'
        outdir = None
        safety = 'max'
    else:
        # argparse section
        parser = argparse.ArgumentParser(
            description='Extract and save attachments ' \
                        'from an invoice in "xml" format.',
            formatter_class=argparse.RawTextHelpFormatter
            )
        parser.add_argument('path',
                            help='A file or a folder to be parsed.')
        parser.add_argument('-o', '--outdir', help='Output directory')
        parser.add_argument('-s', '--safety',
                            help='(default: "max") ' \
                                 'If file already exists:\n' \
                                 '    "max" == do *not* overwrite.\n' \
                                 '    "low" == overwrite',
                            choices=['low', 'max'],
                            default='max')
        args = parser.parse_args()
        path = args.path
        outdir = args.outdir
        safety = args.safety
    # Actual `main`
    for file in yield_xml_files(path):
        for attachment in yield_decoded_attachment(list_attachments(file)):
            write_attachment(attachment, outdir=outdir, safety=safety)


if __name__ == '__main__':
    main()