from __future__ import unicode_literals

import re

from requests.adapters import ConnectionError

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.mail import send_mail
from django.core.urlresolvers import reverse
from django.http import Http404, HttpResponseRedirect
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.utils.http import urlquote
from django.utils.translation import (
    LANGUAGE_SESSION_KEY, ugettext as _, activate,
    get_language_from_request, check_for_language
)

from usersettings.shortcuts import get_current_usersettings

from candidates.models.auth import (
    NameChangeDisallowedException,
    ChangeToLockedConstituencyDisallowedException
)


class DisallowedUpdateMiddleware(object):

    def process_exception(self, request, exc):
        if isinstance(exc, NameChangeDisallowedException):
            usersettings = get_current_usersettings()
            intro = _('As a precaution, an update was blocked:')
            outro = _('If this update is appropriate, someone should apply it manually.')
            # Then email the support address about the name change...
            message = '{intro}\n\n  {message}\n\n{outro}'.format(
                intro=intro,
                message=exc,
                outro=outro,
            )
            send_mail(
                _('Disallowed {site_name} update for checking').format(
                    site_name=Site.objects.get_current().name
                ),
                message,
                usersettings.DEFAULT_FROM_EMAIL,
                [usersettings.SUPPORT_EMAIL],
                fail_silently=False
            )
            # And redirect to a page explaining to the user what has happened
            disallowed_explanation_url = reverse('update-disallowed')
            return HttpResponseRedirect(disallowed_explanation_url)
        elif isinstance(exc, ChangeToLockedConstituencyDisallowedException):
            return HttpResponseForbidden()


class CopyrightAssignmentMiddleware(object):
    """Check that authenticated users have agreed to copyright assigment

    This must come after AuthenticationMiddleware so that request.user
    is present.

    If this is an authenticated user, then insist that they agree to
    assign copyright of any contributions to the COPYRIGHT_HOLDER in
    settings.
    """

    EXCLUDED_PATHS = (
        re.compile(r'^/copyright-question'),
        re.compile(r'^/accounts/'),
        re.compile(r'^/admin/'),
        re.compile(r'^/settings/'),
    )

    def process_request(self, request):
        for path_re in self.EXCLUDED_PATHS:
            if path_re.search(request.path):
                return None
        if not request.user.is_authenticated():
            return None
        already_assigned = request.user.terms_agreement.assigned_to_dc
        if already_assigned:
            return None
        else:
            # Then redirect to a view that asks you to assign
            # copyright:
            assign_copyright_url = reverse('ask-for-copyright-assignment')
            assign_copyright_url += "?next={0}".format(
                urlquote(request.path)
            )
            return HttpResponseRedirect(assign_copyright_url)


class SetLanguage(object):
    def process_request(self, request):
        # this largely duplicates the code in get_language_from_request
        # but without falling back to the default settings.LANGUAGE
        # becuase we don't want to do that
        language = None

        # check if the user has set a language preference
        if hasattr(request, 'session') and \
                LANGUAGE_SESSION_KEY in request.session:
            language = request.session[LANGUAGE_SESSION_KEY]
        # or if they've set the language in a cookie
        elif settings.LANGUAGE_COOKIE_NAME in request.COOKIES:
            language = request.COOKIES[settings.LANGUAGE_COOKIE_NAME]
        # or if they have an Accept-Language header
        else:
            language = request.META.get('HTTP_ACCEPT_LANGUAGE', None)

        # Now check to see if we got a language and it's supported
        if language is not None and check_for_language(language):
            return None

        # otherwise set to the default language from site settings
        user_settings = get_current_usersettings()
        request.LANGUAGE_CODE = user_settings.LANGUAGE
        activate(request.LANGUAGE_CODE)

        return None
