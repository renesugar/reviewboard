import httplib
from django.utils import simplejson
from reviewboard.scmtools.errors import FileNotFoundError
                                 '%(github_public_repo_name)s/issues#issue/%%s',
    supports_bug_trackers = True
        except Exception, e:
            if str(e) == 'Not Found':
                        _('A repository with this organization or name was not '
                          'found.'))
                body=simplejson.dumps(body))
        except (urllib2.HTTPError, urllib2.URLError), e:
                rsp = simplejson.loads(data)
                raise AuthorizationError(str(e))
                except HostingServiceError, e:
                    if str(e) != 'Not Found':
        except (urllib2.URLError, urllib2.HTTPError):
        except (urllib2.URLError, urllib2.HTTPError):
        elif 'errors' in rsp and status_code == httplib.UNPROCESSABLE_ENTITY:
                                   owner, repo_name)
        except (urllib2.URLError, urllib2.HTTPError), e:
        except (urllib2.URLError, urllib2.HTTPError), e:
        except (urllib2.URLError, urllib2.HTTPError), e:
            rsp = simplejson.loads(data)
            raise HostingServiceError(str(e))