#! /usr/bin/env python

import optparse
import os
import re
import subprocess

import git
from wake import Vulture


def parse_args():
    def csv(option, opt, value, parser):
        setattr(parser.values, option.dest, value.split(','))
    def regex_csv(option, opt, value, parser):
        setattr(parser.values, option.dest, map(re.compile, value.split(',')))
    usage = "usage: %prog [options] PATH [PATH ...]"
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--exclude', action='callback', callback=csv,
                      type="string", default=[],
                      help='Comma-separated list of filename patterns to '
                           'exclude (e.g. svn,external).')
    parser.add_option('--exclude-identifier-regexes',
                      action='callback', callback=regex_csv,
                      type="string", default=[],
                      help='Comma-separated list of identifier regexes to '
                           'exclude (e.g. "Test,^test_").')
    parser.add_option('-v', '--verbose', action='store_true')
    options, args = parser.parse_args()
    return options, args


class GitVulture(Vulture):

    @property
    def all_unused_items(self):
        def file_lineno(item):
            return (item.file.lower(), item.lineno)
        return sorted(self.unused_funcs + self.unused_props +
                      self.unused_vars + self.unused_attrs,
                      key=file_lineno)


def _path_for_item(item):
    relpath = os.path.relpath(item.file)
    return  relpath if not relpath.startswith('..') else item.file


if __name__ == '__main__':
    options, args = parse_args()
    vulture = GitVulture(exclude=options.exclude, verbose=False and options.verbose)
    vulture.scavenge(args)
    for item in vulture.all_unused_items:
        if any(regex.search(item) for regex in options.exclude_identifier_regexes):
            continue
        file_dir = os.path.dirname(item.file)
        process = subprocess.Popen([
            'git', 'grep',

            # '-q',  # From the git-grep manpage:
            #        # > exit with status 0 when there is a match and with
            #        # > non-zero status when there isn't.
            '-ch',   # Only output counts.
                     # TODO: figure out how to get git to aggregate the counts.
            '-I',    # ignore matches in binary files

            item,    # Item subclasses str, so can be passed directly
        ], cwd=git.Repo(file_dir).wd, stdout=subprocess.PIPE)
        process.wait()
        num_found = sum(map(int, process.stdout.read().strip().split('\n')))
        pretty_path = _path_for_item(item)
        if num_found == 0:
            # This shouldn't happen, since the file should be in the repo.
            # TODO: Handle untracked content? That might really slow down
            # git-grep
            raise AssertionError('Unused %s not found at all in git-grep!')
        elif num_found == 1:
            # This implies that the usage we found was the *only* usage, so
            # output it.

            print(
                "{path}:{item.lineno}: Unused {item.typ} '{item}' "
                "(used {num_found} times in git-grep)".format(
                    item=item, path=pretty_path, num_found=num_found))
        else:
            # This implies that the usage we found was not the only usage, but
            # vulture missed other usages because of things like template
            # files or tests. Only output if in verbose mose.
            if options.verbose:
                print("SKIPPING DUE TO USAGES: "
                    "{path}:{item.lineno}: Unused {item.typ} '{item}' "
                    "(used {num_found} times in git-grep)".format(
                        item=item, path=pretty_path, num_found=num_found))


# ./git_vulture.py --exclude */migrations/* $WORKDIR --exclude-identifier-regexes='^test,Test,^clean'
