import json

from django.conf.urls import url
from django.contrib import messages
from django.contrib.admin.views.main import ChangeList
from django.core.exceptions import FieldError, ValidationError
from django.forms import Media
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views.generic import TemplateView
from django.http import HttpResponseNotFound

from .compat import text_type
from .exceptions import DjangoQLError
from .queryset import apply_search
from .schema import DjangoQLSchema

try:
    from django.core.urlresolvers import reverse
except ImportError:  # Django 2.0
    from django.urls import reverse


DJANGOQL_SEARCH_MARKER = 'q-l'


class DjangoQLChangeList(ChangeList):
    def get_filters_params(self, *args, **kwargs):
        params = super(DjangoQLChangeList, self).get_filters_params(
            *args,
            **kwargs
        )
        if DJANGOQL_SEARCH_MARKER in params:
            del params[DJANGOQL_SEARCH_MARKER]
        return params


class DjangoQLSearchMixin(object):
    search_fields = ('_djangoql',)  # just a stub to have search input displayed
    djangoql_completion = True
    djangoql_schema = DjangoQLSchema
    djangoql_syntax_help_template = 'djangoql/syntax_help.html'

    def search_mode_toggle_enabled(self):
        # If search fields were defined on a child ModelAdmin instance,
        # we suppose that the developer wants two search modes and therefore
        # enable search mode toggle
        return self.search_fields != DjangoQLSearchMixin.search_fields

    def djangoql_search_enabled(self, request):
        return request.GET.get(DJANGOQL_SEARCH_MARKER, '').lower() == 'on'

    def get_changelist(self, *args, **kwargs):
        return DjangoQLChangeList

    def get_search_results(self, request, queryset, search_term):
        if (
            self.search_mode_toggle_enabled() and
            not self.djangoql_search_enabled(request)
        ):
            return super(DjangoQLSearchMixin, self).get_search_results(
                request=request,
                queryset=queryset,
                search_term=search_term,
            )
        use_distinct = False
        if not search_term:
            return queryset, use_distinct
        try:
            return (
                apply_search(queryset, search_term, self.djangoql_schema),
                use_distinct,
            )
        except (DjangoQLError, ValueError, FieldError, ValidationError) as e:
            msg = self.djangoql_error_message(e)
            messages.add_message(request, messages.WARNING, msg)
            return queryset.none(), use_distinct

    def djangoql_error_message(self, exception):
        if isinstance(exception, ValidationError):
            msg = exception.messages[0]
        else:
            msg = text_type(exception)
        return render_to_string('djangoql/error_message.html', context={
            'error_message': msg,
        })

    @property
    def media(self):
        media = super(DjangoQLSearchMixin, self).media
        if self.djangoql_completion:
            js = [
                'djangoql/js/lib/lexer.js',
                'djangoql/js/completion.js',
            ]
            if self.search_mode_toggle_enabled():
                js.append('djangoql/js/completion_admin_toggle.js')
            js.append('djangoql/js/completion_admin.js')
            media += Media(
                css={'': (
                    'djangoql/css/completion.css',
                    'djangoql/css/completion_admin.css',
                )},
                js=js,
            )
        return media

    def get_urls(self):
        custom_urls = []
        if self.djangoql_completion:
            custom_urls += [
                url(
                    r'^introspect/$',
                    self.admin_site.admin_view(self.introspect),
                    name='%s_%s_djangoql_introspect' % (
                        self.model._meta.app_label,
                        self.model._meta.model_name,
                    ),
                ),
                url(
                    r'^djangoql-syntax/$',
                    self.admin_site.admin_view(TemplateView.as_view(
                        template_name=self.djangoql_syntax_help_template,
                    )),
                    name='djangoql_syntax_help',
                ),
                url(
                    r'^suggestions/(?P<model>[\w\.]+)/(?P<field>\w+)/(?P<page>\d+)$',
                    self.admin_site.admin_view(self.suggestions),
                    name='%s_%s_suggestions' % (
                        self.model._meta.app_label,
                        self.model._meta.model_name,
                    ),
                ),
            ]
        return custom_urls + super(DjangoQLSearchMixin, self).get_urls()

    def introspect(self, request):
        response = self.djangoql_schema(self.model).as_dict()
        return HttpResponse(
            content=json.dumps(response, indent=2),
            content_type='application/json; charset=utf-8',
        )

    def suggestions(self, request, *args, **kwargs):
        schema = self.djangoql_schema(self.model)
        model_name = kwargs["model"]
        field_name = kwargs["field"]
        page = kwargs["page"]
        model = schema.models.get(model_name)
        if model is None:
            return HttpResponseNotFound(
                content="Model not found",
                content_type='application/json; charset=utf-8',
            )
        field = model.get(field_name)
        if field is None:
            return HttpResponseNotFound(
                content="No such field",
                content_type='application/json; charset=utf-8',
            )
        response = field.get_paginated_options(page)
        return HttpResponse(
            content=json.dumps(response, indent=2),
            content_type='application/json; charset=utf-8',
        )
