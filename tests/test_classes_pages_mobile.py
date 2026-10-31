"""Classes & Subjects, Subject Library and Archived Subjects on phones.

Same HTML for every screen size: these tests check the pieces the phone layout
needs (header classes, labelled table cells, one-per-line subject chips, the
shared phone styles) and that no desktop feature went missing."""


def _source(app, name):
    return app.jinja_env.loader.get_source(app.jinja_env, name)[0]


def test_shared_phone_styles_are_served(client):
    css = client.get('/static/style.css').get_data(as_text=True)
    for needle in ('.m-head', '.m-actions', '.m-tap', '.m-cards',
                   'content: attr(data-label)'):
        assert needle in css, needle


def test_classes_page_phone_layout(admin_client, seed):
    body = admin_client.get('/classes').get_data(as_text=True)
    assert 'dashboard-header m-head' in body
    assert 'm-actions' in body
    assert '.accordion-button .ms-auto' in body          # badges drop under the class name
    assert 'col-12 col-sm-6' in body                       # subject chips: one per line on phones
    assert 'class="col-6">' not in body.split('<!-- Subjects column -->', 1)[1].split('PER-CLASS MODALS', 1)[0]


def test_classes_page_features_are_still_there(admin_client, seed):
    body = admin_client.get('/classes').get_data(as_text=True)
    for needle in ('id="viewListBtn"', 'id="viewGridBtn"', 'id="addClassModal"',
                   'Subject Library', 'Archived Subjects', 'id="classAccordion"',
                   'id="gridView"'):
        assert needle in body, needle


def test_subject_library_phone_layout(admin_client, app, seed):
    body = admin_client.get('/subjects/library').get_data(as_text=True)
    assert 'dashboard-header m-head' in body
    assert 'd-flex flex-wrap gap-2 m-actions' in body
    assert 'id="addLibrarySubjectModal"' in body
    source = _source(app, 'subject_library.html')
    assert 'align-middle mb-0 m-cards' in source
    for label in ('Code', 'Classes offering it', 'Archived class rows',
                  'Tests using it', 'Default for new classes', 'Actions'):
        assert 'data-label="%s"' % label in source, label
    assert source.count('m-tap') >= 4                      # star, rename, archive, restore


def test_archived_subjects_phone_layout(admin_client, app, seed):
    body = admin_client.get('/subjects/archived').get_data(as_text=True)
    assert 'dashboard-header m-head' in body
    assert 'Back to Classes' in body
    source = _source(app, 'archived_subjects.html')
    assert 'align-middle mb-0 m-cards' in source
    for label in ('Class', 'Subject Teacher', 'Tests using it', 'Actions'):
        assert 'data-label="%s"' % label in source, label
