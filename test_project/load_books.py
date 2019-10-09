import argparse
import os
from os.path import (dirname, join, exists)
import csv
import datetime


def makeup_genre(i, book):
    name = book["original_title"].lower()
    if "d" in name[:10]:
        return 1
    elif "c" in name[:10]:
        return 2
    else:
        return 3

def date_from_year(year_string):
    try:
        return datetime.datetime(int(year_string[:4]), 1, 1)
    except ValueError:
        return datetime.datetime(2000, 1, 1)

def makeup_published(i):
    return bool(i % 50)

def make_object_id(isbn):
    try:
        return int(isbn)
    except ValueError:
        return None

def parse_csv(path_to_csv):
    from core.models import Book
    from django.contrib.auth import get_user_model
    # from django.contrib.auth.models import User

    User = get_user_model()


    User.objects.filter(is_staff=False).delete()
    Book.objects.all().delete()

    # User.objects.create_superuser("tema", "putilkin@gmail.com", "123321")

    authors_buffer = {}
    similar_buffer = {}

    with open(path_to_csv, newline='') as f:
        booksreader = csv.DictReader(f)
        for i, book in enumerate(booksreader):
            if i > 100:
                break
            authors = book["authors"][:150]
            name = book["original_title"]
            if authors == "" or name == "":
                continue
            rating_string = book["average_rating"]
            if authors not in authors_buffer:
                user = User.objects.create_user(username=authors)
                authors_buffer[authors] = user
            else:
                user = authors_buffer[authors]
            book_instance = Book(
                name = name,
                author = user,
                genre = makeup_genre(i, book),
                written = date_from_year(book["original_publication_year"]),
                is_published = makeup_published(i),
                rating = book["average_rating"],
                price = book["books_count"],
                object_id = make_object_id(book["isbn"])
            )
            try:
                book_instance.save()
                similar_books = similar_buffer.setdefault(rating_string, [])
                if len(similar_books) > 0:
                    book_instance.similar_books.add(*similar_books)
                similar_books.append(book_instance)
            except:
                print("Error saving %s" % book_instance.name)
                book_instance.save()









def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "test_project.settings")
    parser = argparse.ArgumentParser("load_books")
    parser.add_argument("path", type=str, help="Path to csv table with books")
    args = parser.parse_args()
    if not exists(args.path):
        raise ValueError("Csv file not found")
    import django
    django.setup()
    parse_csv(args.path)

if __name__ == "__main__":
    main()