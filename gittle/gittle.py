# Python imports
import os
import copy

# Dulwich imports
from dulwich.repo import Repo as DRepo
from dulwich.client import get_transport_and_path
from dulwich.index import build_index_from_tree

# Local imports
from . import utils


class Gittle(object):
    DEFAULT_MESSAGE = '**No Message**'
    DEFAULT_USER_INFO = {
        'name': None,
        'email': None,
    }

    HIDDEN_REGEXES = [
        # Hide git directory
        r'./.git/',
    ]

    def __init__(self, repo_or_path):
        if isinstance(repo_or_path, DRepo):
            self.repo = repo_or_path
        elif isinstance(repo_or_path, basestring):
            self.repo = DRepo(repo_or_path)
        else:
            raise Exception('Gittle must be initialized with either a dulwich repository or a string to the path')

        # Set path
        self.path = self.repo.path

        # Build ignore filter
        self.hidden_regexes = copy.copy(self.HIDDEN_REGEXES)
        self.hidden_regexes.extend(self._get_ignore_regexes())
        self.ignore_filter = utils.path_filter_regex(self.hidden_regexes)
        self.filters = [
            self.ignore_filter,
        ]

    def _get_ignore_regexes(self):
        gitignore_filename = os.path.join(self.path, '.gitignore')
        if not os.path.exists(gitignore_filename):
            return []
        lines = open(gitignore_filename).readlines()
        globers = map(lambda line: line.rstrip(), lines)
        return utils.globers_to_regex(globers)

    @property
    def last_commit(self):
        return self.repo[self.repo.head()]

    @property
    def index(self):
        return self.repo.open_index()

    @classmethod
    def init(cls, path):
        """Initialize a repository"""
        repo = DRepo.init(path)
        return cls(repo)

    @classmethod
    def init_bare(cls, path):
        repo = DRepo.init_bare(path)
        return cls(repo)

    @classmethod
    def clone_remote(cls, remote_path, local_path, mkdir=True, **kwargs):
        """Clone a remote repository"""

        if mkdir and not(os.path.exists(local_path)):
            os.makedirs(local_path)

        # Initialize the local repository
        local_repo = DRepo.init(local_path)

        # Get client
        client, host_path = get_transport_and_path(remote_path, **kwargs)

        # Fetch data from remote repository
        remote_refs = client.fetch(host_path, local_repo)

        # Update head
        local_repo["HEAD"] = remote_refs["HEAD"]

        # Rebuild index
        build_index_from_tree(local_repo.path, local_repo.index_path(),
                        local_repo.object_store, local_repo['HEAD'].tree)

        # Add origin
        return cls(local_repo)

    @classmethod
    def clone(cls):
        """Clone a local repository"""
        pass

    def _commit(self, commiter=None, author=None, message=None, *args, **kwargs):
        message = message or self.DEFAULT_MESSAGE
        return self.repo.do_commit(
            message=message,
            author=author,
            commmiter=commiter)

    # Like: git commmit -a
    def commit(self, name=None, email=None, message=None):
        user_info = {
            'name': name,
            'email': email,
        }
        return self._commit(
            commiter=user_info,
            author=user_info,
            message=message)

    # Commit only a set of files
    def commit_files(self):
        pass

    @property
    @utils.transform(set)
    def tracked_files(self):
        return self.index._byname.keys()

    @property
    @utils.transform(set)
    def raw_files(self):
        return utils.subpaths(self.path)

    @property
    @utils.transform(set)
    def ignored_files(self):
        return utils.subpaths(self.path, filters=self.filters)

    @property
    @utils.transform(set)
    def trackable_files(self):
        return self.raw_files - self.ignored_files

    @property
    @utils.transform(set)
    def untracked_files(self):
        return self.trackable_files - self.tracked_files

    @property
    @utils.transform(set)
    def modified_staged_files(self):
        """Checks if the file has changed since last commit"""
        timestamp = self.last_commit.commit_time
        index = self.index
        return [
            f
            for f in self.tracked_files
            if index[f][1][0] > timestamp
        ]

    @property
    @utils.transform(set)
    def modified_unstaged_files(self):
        timestamp = self.last_commit.commit_time
        return [
            f
            for f in self.tracked_files
            if os.stat(f).st_mtime > timestamp
        ]

    @property
    @utils.transform(set)
    def modified_files(self):
        return self.modified_staged_files | self.modified_unstaged_files

    # Like: git add
    @utils.arglist_method
    def add(self, files):
        return self.repo.stage(files)

    # Like: git rm
    @utils.arglist_method
    def rm(self, files, force=False):
        index = self.index
        index_files = filter(lambda f: f in index, files)
        for f in index_files:
            del self.index[f]
        return index.write()

    # Move file in the git index
    def mv_index(self, file_pair):
        old_name, new_name = file_pair
        index = self.index
        entry = index[old_name]
        index[new_name] = entry
        del index[old_name]

    def mv_fs(self, file_pair):
        old_name, new_name = file_pair
        os.rename(old_name, new_name)

    # Like: git mv
    @utils.arglist_method
    def mv(self, files_pair):
        index = self.index
        files_in_index = filter(lambda f: f[0] in index, files_pair)
        map(self.mv_index, files_in_index)
        map(self.mv_fs, files_in_index)
        return index.write()

    @utils.arglist_method
    def checkout(self, files):
        pass

    @utils.arglist_method
    def reset(self, files, commit='HEAD'):
        pass

    def rm_all(self):
        self.index.clear()
        return self.index.write()
