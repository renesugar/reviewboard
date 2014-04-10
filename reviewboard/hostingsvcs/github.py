from __future__ import unicode_literals

import json
import uuid
from collections import defaultdict
from django.conf.urls import patterns, url
from django.core.cache import cache
from django.http import HttpResponse
from django.utils import six
from django.utils.six.moves import http_client
from django.utils.six.moves.urllib.error import HTTPError, URLError
from django.views.decorators.http import require_POST
                                            HostingServiceError,
from reviewboard.hostingsvcs.hook_utils import (close_all_review_requests,
                                                get_git_branch_name,
                                                get_review_request_id,
                                                get_server_url)
from reviewboard.scmtools.core import Branch, Commit
from reviewboard.scmtools.errors import FileNotFoundError, SCMError
                                 '%(github_public_repo_name)s/'
                                 'issues#issue/%%s',
    supports_post_commit = True
    supports_repositories = True
    repository_url_patterns = patterns(
        '',

        url(r'^hooks/post-receive/$',
            'reviewboard.hostingsvcs.github._process_post_receive_hook'),
    )

        except Exception as e:
            if six.text_type(e) == 'Not Found':
                        _('A repository with this organization or name was '
                          'not found.'))
        site_base_url = '%s%s' % (
        site_url = '%s://%s' % (siteconfig.get('site_domain_method'),
                                site_base_url)

        note = 'Access for Review Board (%s - %s)' % (
            site_base_url,
            uuid.uuid4().hex[:7])

                'note': note,
                body=json.dumps(body))
        except (HTTPError, URLError) as e:
                rsp = json.loads(data)
                raise AuthorizationError(six.text_type(e))
        self._save_auth_data(rsp)
    def get_reset_auth_token_requires_password(self):
        """Returns whether or not resetting the auth token requires a password.

        A password will be required if not using a GitHub client ID or
        secret.
        """
        if not self.is_authorized():
            return True

        app_info = self.account.data['authorization']['app']
        client_id = app_info.get('client_id', '')
        has_client = (client_id.strip('0') != '')

        return (not has_client or
                (not (hasattr(settings, 'GITHUB_CLIENT_ID') and
                      hasattr(settings, 'GITHUB_CLIENT_SECRET'))))

    def reset_auth_token(self, password=None, two_factor_auth_code=None):
        """Resets the authorization token for the linked account.

        This will attempt to reset the token in a few different ways,
        depending on how the token was granted.

        Tokens linked to a registered GitHub OAuth app can be reset without
        requiring any additional credentials.

        Tokens linked to a personal account (which is the case on most
        installations) require a password and possibly a two-factor auth
        code. Callers should call get_reset_auth_token_requires_password()
        before determining whether to pass a password, and should pass
        a two-factor auth code if this raises TwoFactorAuthCodeRequiredError.
        """
        if self.is_authorized():
            token = self.account.data['authorization']['token']
        else:
            token = None

        if self.get_reset_auth_token_requires_password():
            assert password

            if self.account.local_site:
                local_site_name = self.account.local_site.name
            else:
                local_site_name = None

            if token:
                try:
                    self._delete_auth_token(
                        self.account.data['authorization']['id'],
                        password=password,
                        two_factor_auth_code=two_factor_auth_code)
                except HostingServiceError as e:
                    # If we get a Not Found, then the authorization was
                    # probably already deleted.
                    if six.text_type(e) != 'Not Found':
                        raise

                self.account.data['authorization'] = ''
                self.account.save()

            # This may produce errors, which we want to bubble up.
            self.authorize(self.account.username, password,
                           self.account.hosting_url,
                           two_factor_auth_code=two_factor_auth_code,
                           local_site_name=local_site_name)
        else:
            # We can use the new API for resetting the token without
            # re-authenticating.
            auth_data = self._reset_authorization(
                settings.GITHUB_CLIENT_ID,
                settings.GITHUB_CLIENT_SECRET,
                token)
            self._save_auth_data(auth_data)

        except (URLError, HTTPError):
        except (URLError, HTTPError):
    def get_branches(self, repository):
        results = []

        url = self._build_api_url(self._get_repo_api_url(repository),
                                  'git/refs/heads')

        try:
            rsp = self._api_get(url)
        except Exception as e:
            logging.warning('Failed to fetch commits from %s: %s',
                            url, e)
            return results

        for ref in rsp:
            refname = ref['ref']

            if not refname.startswith('refs/heads/'):
                continue

            name = refname.split('/')[-1]
            results.append(Branch(name, ref['object']['sha'],
                                  default=(name == 'master')))

        return results

    def get_commits(self, repository, start=None):
        results = []

        resource = 'commits'
        url = self._build_api_url(self._get_repo_api_url(repository), resource)

        if start:
            url += '&sha=%s' % start

        try:
            rsp = self._api_get(url)
        except Exception as e:
            logging.warning('Failed to fetch commits from %s: %s',
                            url, e)
            return results

        for item in rsp:
            commit = Commit(
                item['commit']['author']['name'],
                item['sha'],
                item['commit']['committer']['date'],
                item['commit']['message'])
            if item['parents']:
                commit.parent = item['parents'][0]['sha']

            results.append(commit)

        return results

    def get_change(self, repository, revision):
        repo_api_url = self._get_repo_api_url(repository)

        # Step 1: fetch the commit itself that we want to review, to get
        # the parent SHA and the commit message. Hopefully this information
        # is still in cache so we don't have to fetch it again.
        commit = cache.get(repository.get_commit_cache_key(revision))
        if commit:
            author_name = commit.author_name
            date = commit.date
            parent_revision = commit.parent
            message = commit.message
        else:
            url = self._build_api_url(repo_api_url, 'commits')
            url += '&sha=%s' % revision

            try:
                commit = self._api_get(url)[0]
            except Exception as e:
                raise SCMError(six.text_type(e))

            author_name = commit['commit']['author']['name']
            date = commit['commit']['committer']['date'],
            parent_revision = commit['parents'][0]['sha']
            message = commit['commit']['message']

        # Step 2: fetch the "compare two commits" API to get the diff if the
        # commit has a parent commit. Otherwise, fetch the commit itself.
        if parent_revision:
            url = self._build_api_url(
                repo_api_url, 'compare/%s...%s' % (parent_revision, revision))
        else:
            url = self._build_api_url(repo_api_url, 'commits/%s' % revision)

        try:
            comparison = self._api_get(url)
        except Exception as e:
            raise SCMError(six.text_type(e))

        if parent_revision:
            tree_sha = comparison['base_commit']['commit']['tree']['sha']
        else:
            tree_sha = comparison['commit']['tree']['sha']

        files = comparison['files']

        # Step 3: fetch the tree for the original commit, so that we can get
        # full blob SHAs for each of the files in the diff.
        url = self._build_api_url(repo_api_url, 'git/trees/%s' % tree_sha)
        url += '&recursive=1'
        tree = self._api_get(url)

        file_shas = {}
        for file in tree['tree']:
            file_shas[file['path']] = file['sha']

        diff = []

        for file in files:
            filename = file['filename']
            status = file['status']
            try:
                patch = file['patch']
            except KeyError:
                continue

            diff.append('diff --git a/%s b/%s' % (filename, filename))

            if status == 'modified':
                old_sha = file_shas[filename]
                new_sha = file['sha']
                diff.append('index %s..%s 100644' % (old_sha, new_sha))
                diff.append('--- a/%s' % filename)
                diff.append('+++ b/%s' % filename)
            elif status == 'added':
                new_sha = file['sha']

                diff.append('new file mode 100644')
                diff.append('index %s..%s' % ('0' * 40, new_sha))
                diff.append('--- /dev/null')
                diff.append('+++ b/%s' % filename)
            elif status == 'removed':
                old_sha = file_shas[filename]

                diff.append('deleted file mode 100644')
                diff.append('index %s..%s' % (old_sha, '0' * 40))
                diff.append('--- a/%s' % filename)
                diff.append('+++ /dev/null')

            diff.append(patch)

        diff = '\n'.join(diff)

        # Make sure there's a trailing newline
        if not diff.endswith('\n'):
            diff += '\n'

        return Commit(author_name, revision, date, message, parent_revision,
                      diff=diff)

    def _reset_authorization(self, client_id, client_secret, token):
        """Resets the authorization info for an OAuth app-linked token.

        If the token is associated with a registered OAuth application,
        its token will be reset, without any authentication details required.
        """
        url = '%sapplications/%s/tokens/%s' % (
            self.get_api_url(self.account.hosting_url),
            client_id,
            token)

        # Allow any errors to bubble up
        return self._api_post(url=url,
                              username=client_id,
                              password=client_secret)

    def _delete_auth_token(self, auth_id, password, two_factor_auth_code=None):
        """Requests that an authorization token be deleted.

        This will delete the authorization token with the given ID. It
        requires a password and, depending on the settings, a two-factor
        authentication code to perform the deletion.
        """
        headers = {}

        if two_factor_auth_code:
            headers['X-GitHub-OTP'] = two_factor_auth_code

        url = self._build_api_url(
            '%sauthorizations/%s' % (
                self.get_api_url(self.account.hosting_url),
                auth_id))

        self._api_delete(url=url,
                         headers=headers,
                         username=self.account.username,
                         password=password)

    def _save_auth_data(self, auth_data):
        """Saves authorization data sent from GitHub."""
        self.account.data['authorization'] = auth_data
        self.account.save()

        elif ('errors' in rsp and
              status_code == http_client.UNPROCESSABLE_ENTITY):
                                  owner, repo_name)
    def _api_get(self, url, *args, **kwargs):
            data, headers = self._json_get(url, *args, **kwargs)
            return data
        except (URLError, HTTPError) as e:
            self._check_api_error(e)
    def _api_post(self, url, *args, **kwargs):
        try:
            data, headers = self._json_post(url, *args, **kwargs)
            return data
        except (URLError, HTTPError) as e:
            self._check_api_error(e)
    def _api_delete(self, url, *args, **kwargs):
        try:
            data, headers = self._json_delete(url, *args, **kwargs)
            return data
        except (URLError, HTTPError) as e:
            self._check_api_error(e)

    def _check_api_error(self, e):
        data = e.read()

        try:
            rsp = json.loads(data)
        except:
            rsp = None

        if rsp and 'message' in rsp:
            response_info = e.info()
            x_github_otp = response_info.get('X-GitHub-OTP', '')

            if x_github_otp.startswith('required;'):
                raise TwoFactorAuthCodeRequiredError(
                    _('Enter your two-factor authentication code. '
                      'This code will be sent to you by GitHub.'))

            if e.code == 401:
                raise AuthorizationError(rsp['message'])

            raise HostingServiceError(rsp['message'])
        else:
            raise HostingServiceError(six.text_type(e))


@require_POST
def _process_post_receive_hook(request, *args, **kwargs):
    """Closes review requests as submitted automatically after a push."""
    try:
        payload = json.loads(request.body)
    except ValueError as e:
        logging.error('The payload is not in JSON format: %s', e)
        return HttpResponse(status=415)

    server_url = get_server_url(request)
    review_id_to_commits = _get_review_id_to_commits_map(payload, server_url)

    if not review_id_to_commits:
        return HttpResponse()

    close_all_review_requests(review_id_to_commits)

    return HttpResponse()


def _get_review_id_to_commits_map(payload, server_url):
    """Returns a dictionary, mapping a review request ID to a list of commits.

    If a commit's commit message does not contain a review request ID, we append
    the commit to the key None.
    """
    review_id_to_commits_map = defaultdict(list)

    ref_name = payload.get('ref', None)
    branch_name = get_git_branch_name(ref_name)

    if not branch_name:
        return None

    commits = payload.get('commits', [])

    for commit in commits:
        commit_hash = commit.get('id', None)
        commit_message = commit.get('message', None)
        review_request_id = get_review_request_id(commit_message, server_url,
                                                  commit_hash)

        commit_entry = '%s (%s)' % (branch_name, commit_hash[:7])
        review_id_to_commits_map[review_request_id].append(commit_entry)

    return review_id_to_commits_map