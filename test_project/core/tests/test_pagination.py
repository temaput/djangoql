import json

from django.apps import apps
from django.contrib.auth.models import Group, User
from django.test import TestCase

from djangoql.exceptions import DjangoQLSchemaError
from djangoql.parser import DjangoQLParser
from djangoql.schema import DjangoQLSchema, IntField
try:
    from django.core.urlresolvers import reverse
except ImportError:  # Django 2.0
    from django.urls import reverse


from ..models import Book


class BookCustomFieldsSchema(DjangoQLSchema):
    suggest_options = {
        Book: ['genre', 'name', 'author'],
        User: ['username']
    }

    def get_fields(self, model):
        if model == Book:
            return ['name', 'genre', 'author']
        return super(BookCustomFieldsSchema, self).get_fields(model)


class DjangoQLSuggestionsPaginationTest(TestCase):
    fixtures = ["books_users.xml"]

    def test_get_suggestions(self):
        custom_schema = BookCustomFieldsSchema(Book)
        model = custom_schema.models['core.book']
        name_field = model['name']
        # genre_field = model['genre']

        custom = custom_schema.as_dict()['models']['core.book']
        name = custom["name"]
        genre = custom["genre"]
        self.assertListEqual(genre["options"], ['Drama', 'Comics', 'Other'])
        self.assertEqual(len(name["options"]),
                         name_field.suggest_options_page_size)
        self.assertEqual(name["has_more_options"], True)
        self.assertEqual(name["next_options_page_number"], 2)

    def test_get_suggestions_from_schema(self):
        custom = BookCustomFieldsSchema(Book)
        model = custom.models['core.book']
        name = model['name']
        genre = model['genre']
        self.assertListEqual(genre.get_options(), ['Drama', 'Comics', 'Other'])

        self.assertEqual(len(name.get_options()), 100)

    def test_get_paginated_suggestions(self):
        custom = BookCustomFieldsSchema(Book)
        model = custom.models['core.book']
        name = model['name']
        genre = model['genre']

        options = genre.get_paginated_options()
        self.assertFalse(options["has_more_options"])
        self.assertEqual(options["next_options_page_number"], None)
        self.assertEqual(options["options"],
                         ['Drama', 'Comics', 'Other'])

        options = name.get_paginated_options()
        self.assertTrue(options["has_more_options"])
        self.assertEqual(options["next_options_page_number"], 2)
        self.assertTrue(isinstance(options["options"], list))
        self.assertEqual(len(options["options"]),
                         name.suggest_options_page_size)

        options = name.get_paginated_options(4)
        self.assertFalse(options["has_more_options"])
        self.assertEqual(options["next_options_page_number"], None)
        self.assertEqual(len(options["options"]),
                         name.suggest_options_page_size)

        # check that all options are actually there
        options_list = []
        page1 = name.get_paginated_options()
        page2 = name.get_paginated_options(page1["next_options_page_number"])
        page3 = name.get_paginated_options(page2["next_options_page_number"])
        page4 = name.get_paginated_options(page3["next_options_page_number"])
        options_list.extend(page1["options"])
        options_list.extend(page2["options"])
        options_list.extend(page3["options"])
        options_list.extend(page4["options"])

        full_options_list = list(name.get_options())

        self.assertListEqual(options_list, full_options_list)

    def test_get_paginated_suggestions_wrong_page(self):
        custom = BookCustomFieldsSchema(Book)
        model = custom.models['core.book']
        genre = model['genre']
        options = genre.get_paginated_options(2)
        self.assertFalse(options["has_more_options"])
        self.assertIsNone(options["next_options_page_number"])
        self.assertEqual(len(options["options"]), 0)

    def test_get_paginated_from_related_field(self):
        custom = BookCustomFieldsSchema(Book)
        model = custom.models['auth.user']
        author_username = model["username"]

        options = author_username.get_paginated_options()
        self.assertTrue(options["has_more_options"])
        self.assertEqual(options["next_options_page_number"], 2)
        self.assertTrue(isinstance(options["options"], list))
        self.assertEqual(len(options["options"]),
                         author_username.suggest_options_page_size)

    def test_get_fields(self):
        custom = BookCustomFieldsSchema(Book).as_dict()['models']['core.book']
        self.assertListEqual(list(custom.keys()), ['name', 'genre', 'author'])


class DjangoQLSuggestionsPaginationAdminTest(TestCase):
    fixtures = ["books_users.xml"]

    def setUp(self):
        self.credentials = {'username': 'tema', 'password': '123321'}

    def test_books_suggestions(self):
        url = reverse('admin:core_book_suggestions', kwargs={
            "page": 2,
            "field": "name",
            "model": "core.book"
        })
        # unauthorized request should be redirected
        response = self.client.get(url)
        self.assertEqual(302, response.status_code)
        self.assertTrue(self.client.login(**self.credentials))
        # authorized request should be served
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        suggestions = json.loads(response.content.decode('utf8'))
        self.assertTrue(suggestions['has_more_options'])
        self.assertEqual(suggestions['next_options_page_number'], 3)

        sample_options = Book.objects.order_by(
            "name").values_list("name", flat=True)[25:50]
        self.assertListEqual(suggestions['options'], list(sample_options))

    def test_authors_suggestions(self):
        url = reverse('admin:core_book_suggestions', kwargs={
            "page": 2,
            "field": "username",
            "model": "auth.user"
        })
        self.assertTrue(self.client.login(**self.credentials))
        # authorized request should be served
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        suggestions = json.loads(response.content.decode('utf8'))
        self.assertTrue(suggestions['has_more_options'])
        self.assertEqual(suggestions['next_options_page_number'], 3)

        sample_options = User.objects.order_by(
            "username").values_list("username", flat=True)[25:50]
        self.assertListEqual(suggestions['options'], list(sample_options))

    def test_last_page_suggestions(self):
        url = reverse('admin:core_book_suggestions', kwargs={
            "page": 4,
            "field": "name",
            "model": "core.book"
        })
        self.assertTrue(self.client.login(**self.credentials))
        # authorized request should be served
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        suggestions = json.loads(response.content.decode('utf8'))
        self.assertFalse(suggestions['has_more_options'])
        self.assertEqual(suggestions['next_options_page_number'], None)

        sample_options = Book.objects.order_by(
            "name").values_list("name", flat=True)[75:100]
        self.assertListEqual(suggestions['options'], list(sample_options))
