from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.db import transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.db.models.functions import Lower
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_GET
from io import TextIOWrapper
from .models import (
    Business,
    CSVImportRateLimit,
    DataSource,
    EditRequest, 
    PoliticalData, 
    ProductCategory, 
    ServiceCategory
)
import csv

@login_required
def add_business(request):
    if request.method == 'GET' and request.user.has_perm('companies.can_import_business_csv'):
        return render(request, 'companies/add_business.html', {
            'can_import_csv': True,
            'services': ServiceCategory.objects.all(),
            'products': ProductCategory.objects.all(),
        })
    
    def safe_float(value, default=0.0):
        """Convert string to float, returning default if empty or invalid"""
        try:
            return float(value) if value else default
        except ValueError:
            return default
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                business = Business.objects.create(
                    name=request.POST['name'],
                    website=request.POST['website'],
                    description=request.POST['description'],
                    provides_services=request.POST.get('provides_services') == 'on',
                    provides_products=request.POST.get('provides_products') == 'on',
                )
                
                # Create the political data
                PoliticalData.objects.create(
                    business=business,
                    # Direct donations
                    direct_conservative_total_donations=safe_float(request.POST.get('direct_conservative_total_donations', 0)),
                    direct_liberal_total_donations=safe_float(request.POST.get('direct_liberal_total_donations', 0)),
                    direct_total_donations=safe_float(request.POST.get('direct_total_donations', 0)),
                    direct_america_pac_donor=request.POST.get('direct_america_pac_donor') == 'on',
                    direct_save_america_pac_donor=request.POST.get('direct_save_america_pac_donor') == 'on',
                    
                    # PAC donations
                    affiliated_pac_conservative_total_donations=safe_float(request.POST.get('affiliated_pac_conservative_total_donations', 0)),
                    affiliated_pac_liberal_total_donations=safe_float(request.POST.get('affiliated_pac_liberal_total_donations', 0)),
                    affiliated_pac_total_donations=safe_float(request.POST.get('affiliated_pac_total_donations', 0)),
                    affiliated_pac_america_pac_donor=request.POST.get('affiliated_pac_america_pac_donor') == 'on',
                    affiliated_pac_save_america_pac_donor=request.POST.get('affiliated_pac_save_america_pac_donor') == 'on',
                    
                    # Senior employee donations
                    senior_employee_conservative_total_donations=safe_float(request.POST.get('senior_employee_conservative_total_donations', 0)),
                    senior_employee_liberal_total_donations=safe_float(request.POST.get('senior_employee_liberal_total_donations', 0)),
                    senior_employee_total_donations=safe_float(request.POST.get('senior_employee_total_donations', 0)),
                    senior_employee_trump_donor=request.POST.get('senior_employee_trump_donor') == 'on',
                    senior_employee_america_pac_donor=request.POST.get('senior_employee_america_pac_donor') == 'on',
                    senior_employee_save_america_pac_donor=request.POST.get('senior_employee_save_america_pac_donor') == 'on',
                )

                # Handle data sources
                form_data = {
                    'data_sources': request.POST.getlist('data_sources[]'),
                }

                # Create the data source records
                for source_url in form_data['data_sources']:
                    if source_url:
                        DataSource.objects.get_or_create(
                            business=business,
                            url=source_url,
                            defaults={
                                'reason': 'manual_addition',
                                'is_approved': True
                            }
                        )
                
                # Handle parent company if specified
                parent_name = request.POST.get('parent_company')
                if parent_name:
                    parent, created = Business.objects.get_or_create(
                        name=parent_name,
                        defaults={'description': f'Parent company of {business.name}'}
                    )
                    business.parent_company = parent
                    business.save()
                
                # Handle services and products
                if business.provides_services:
                    business.services.set(request.POST.getlist('services'))
                if business.provides_products:
                    business.products.set(request.POST.getlist('products'))
                
                messages.success(request, 'Business added successfully!')
                return redirect('business_search')

        except Exception as e:
            messages.error(request, f'Error adding business: {str(e)}')
            return render(request, 'companies/add_business.html', {
                'error': str(e),
                'form_data': request.POST,
                'services': ServiceCategory.objects.all(),
                'products': ProductCategory.objects.all(),
            })
            
    return render(request, 'companies/add_business.html', {
        'services': ServiceCategory.objects.all(),
        'products': ProductCategory.objects.all(),
    })

def business_detail(request, slug):
    business = get_object_or_404(
        Business.objects.prefetch_related(
            'services',
            'products',
            'subsidiaries'
        ).select_related(
            'parent_company',
            'politicaldata'  # Add this
        ),
        slug=slug
    )

    # Get a list of approved data sources
    approved_sources = business.data_sources.filter(is_approved=True)
    
    # Get alternative businesses
    alternatives = business.get_alternative_businesses(limit=5)
    
    # Check if there is any political data to display
    has_direct_donations = (
        business.politicaldata and 
        (business.politicaldata.direct_conservative_total_donations or 
         business.politicaldata.direct_liberal_total_donations)
    )
    
    has_pac_donations = (
        business.politicaldata and
        (business.politicaldata.affiliated_pac_conservative_total_donations or 
         business.politicaldata.affiliated_pac_liberal_total_donations)
    )

    has_senior_employee_donations = (
        business.politicaldata and
        (business.politicaldata.senior_employee_trump_donor or
         business.politicaldata.senior_employee_america_pac_donor or
         business.politicaldata.senior_employee_save_america_pac_donor)
    )
    
    return render(request, 'companies/business_detail.html', {
        'business': business,
        'approved_sources': approved_sources,
        'alternatives': alternatives,
        'has_direct_donations': has_direct_donations,
        'has_pac_donations': has_pac_donations,
        'has_senior_employee_donations': has_senior_employee_donations
    })

def business_search(request):
    query = request.GET.get('q', '').strip()
    businesses = Business.objects.none()
    
    if query:
        # Create a query that checks for exact matches and partial matches
        # Use Case/When to assign priority values
        businesses = Business.objects.annotate(
            search_priority=Case(
                # Priority 1: Exact name match (case-insensitive)
                When(name__iexact=query, then=Value(3)),
                # Priority 2: Name contains the query
                When(name__icontains=query, then=Value(2)),
                # Priority 3: Description contains the query
                When(description__icontains=query, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        ).filter(
            # Combine conditions with OR
            Q(name__icontains=query) |
            Q(description__icontains=query)
        ).select_related(
            'politicaldata'
        ).order_by(
            '-search_priority',  # Sort by priority (highest first)
            'name'              # Then alphabetically by name
        )
    
    return render(request, 'companies/business_search.html', {
        'query': query,
        'businesses': businesses,
    })

@login_required
def edit_requests(request):
    user_requests = EditRequest.objects.filter(submitted_by=request.user)
    return render(request, 'companies/edit_requests.html', {
        'edit_requests': user_requests
    })

@require_GET
def filter_categories(request):
    query = request.GET.get('q', '').strip().lower()
    category_type = request.GET.get('type')
    
    if category_type not in ['services', 'products']:
        return JsonResponse({'error': 'Invalid category type'}, status=400)
    
    CategoryModel = ServiceCategory if category_type == 'services' else ProductCategory
    
    if query:
        # First, find all categories that match the query
        matching_categories = CategoryModel.objects.filter(
            name__icontains=query
        )
        
        # Get IDs of matching categories
        matching_ids = set(matching_categories.values_list('id', flat=True))
        
        # For matching parents, get all their children
        child_ids = set(CategoryModel.objects.filter(
            parent__in=matching_categories
        ).values_list('id', flat=True))
        
        # For matching children, get their parents
        parent_ids = set(matching_categories.exclude(
            parent=None
        ).values_list('parent__id', flat=True))
        
        # Combine all IDs
        all_relevant_ids = matching_ids | child_ids | parent_ids
        
        # Get all categories in a single query
        categories = CategoryModel.objects.filter(
            id__in=all_relevant_ids
        ).select_related('parent').order_by('name')
    else:
        # If no query, return all categories
        categories = CategoryModel.objects.all().select_related('parent').order_by('name')
    
    results = []
    for cat in categories:
        category_data = {
            'id': cat.id,
            'name': cat.name,
            'parent_id': cat.parent.id if cat.parent else None,
            'parent_name': cat.parent.name if cat.parent else None
        }
        results.append(category_data)
    
    return JsonResponse({'results': results})

def home(request):
    return render(request, 'companies/home.html')

@login_required
@permission_required('companies.can_import_business_csv')
def import_business(request):
    if request.method == 'POST':
        if not CSVImportRateLimit.can_import(request.user):
            messages.error(request, 'Please wait 30 seconds between imports.')
            return redirect('import_business')

        form_data = {
            'name': request.POST.get('name'),
            'website': request.POST.get('website'),
            'description': request.POST.get('description'),
            'data_sources': request.POST.getlist('data_sources[]'),
            'provides_services': request.POST.get('provides_services') == 'on',
            'provides_products': request.POST.get('provides_products') == 'on',
            'services': request.POST.getlist('services'),
            'products': request.POST.getlist('products'),
        }

        # Validate file extension
        csv_file = request.FILES.get('csv_file')
        if not csv_file or not csv_file.name.endswith('.csv'):
            messages.error(request, 'Please upload a valid CSV file.')
            return render(request, 'companies/import_business.html', {
                'services': ServiceCategory.objects.all(),
                'products': ProductCategory.objects.all(),
                'form_data': form_data
            })

        try:
            with transaction.atomic():
                # Create business first
                business = Business.objects.create(
                    name=form_data['name'],
                    website=form_data['website'],
                    description=form_data['description'],
                    provides_services=form_data['provides_services'],
                    provides_products=form_data['provides_products'],
                )

                if form_data['provides_services']:
                    business.services.set(form_data['services'])
                if form_data['provides_products']:
                    business.products.set(form_data['products'])

                # Process CSV
                csv_text = TextIOWrapper(csv_file, encoding='utf-8')
                reader = csv.DictReader(csv_text)
                
                # Validate CSV structure    
                required_fields = {'Recipient', 'View'}
                if not required_fields.issubset(reader.fieldnames):
                    raise ValueError('CSV file missing required columns')

                # At least one donation type column must exist
                if 'From Organization' not in reader.fieldnames and 'From Individuals' not in reader.fieldnames and 'From PACs' not in reader.fieldnames:
                    raise ValueError('CSV must contain at least one of "From Organization","From Individuals", or "From PACs" columns')
                
                # At least one data source is required
                if not form_data['data_sources']:
                    raise ValueError('At least one data source URL is required')

                if not any(url.strip() for url in form_data['data_sources']):
                    raise ValueError('At least one non-empty data source URL is required')

                # Initialize all counters and flags
                direct_liberal_total = Decimal('0')
                direct_conservative_total = Decimal('0')
                direct_total = Decimal('0')
                pac_liberal_total = Decimal('0')
                pac_conservative_total = Decimal('0')
                pac_total = Decimal('0')
                senior_employee_liberal_total = Decimal('0')
                senior_employee_conservative_total = Decimal('0')
                senior_employee_total = Decimal('0')
                
                direct_america_pac = False
                direct_save_america = False
                pac_america_pac = False
                pac_save_america = False
                senior_employee_america_pac = False
                senior_employee_save_america = False
                senior_employee_trump_donor = False

                for row in reader:
                    view = row['View'].lower()
                    is_liberal = 'democrat' in view or 'liberal' in view
                    is_conservative = 'republican' in view or 'conservative' in view

                    # Process direct donations
                    if 'From Organization' in reader.fieldnames:
                        org_amount = Decimal(row['From Organization'].replace('$', '').replace(',', '') or '0')
                        recipient = row['Recipient'].lower()
                        if org_amount > 0:
                            if is_liberal:
                                direct_liberal_total += org_amount
                            elif is_conservative:
                                direct_conservative_total += org_amount
                            direct_total += org_amount

                            # Check specific donations
                            if 'america pac \(texas\)' in recipient:
                                direct_america_pac = True
                            elif 'save america' in recipient:
                                direct_save_america = True
                            
                    # Process PAC donations 
                    if 'From PACs' in reader.fieldnames:
                        pac_amount = Decimal(row['From PACs'].replace('$', '').replace(',', '') or '0')
                        recipient = row['Recipient'].lower()
                        if pac_amount > 0:
                            if is_liberal:
                                pac_liberal_total += pac_amount
                            elif is_conservative:
                                pac_conservative_total += pac_amount
                            pac_total += pac_amount

                            # Check specific donations
                            if 'trump' in recipient:
                                pac_trump_donor = True
                            elif 'america pac \(texas\)' in recipient:
                                pac_america_pac = True
                            elif 'save america' in recipient:
                                pac_save_america = True

                    # Process senior employee donations
                    if 'From Individuals' in reader.fieldnames:
                        individual_amount = Decimal(row['From Individuals'].replace('$', '').replace(',', '') or '0')
                        recipient = row['Recipient'].lower()
                        if individual_amount > 0:
                            if is_liberal:
                                senior_employee_liberal_total += individual_amount
                            elif is_conservative:
                                senior_employee_conservative_total += individual_amount
                            senior_employee_total += individual_amount

                            # Check specific donations
                            if 'trump' in recipient:
                                senior_employee_trump_donor = True
                            elif 'america pac \(texas\)' in recipient:
                                senior_employee_america_pac = True
                            elif 'save america' in recipient:
                                senior_employee_save_america = True

                # Create political data
                PoliticalData.objects.create(
                    business=business,
                    # Direct donations
                    direct_conservative_total_donations=direct_conservative_total,
                    direct_liberal_total_donations=direct_liberal_total,
                    direct_total_donations=direct_total,
                    direct_america_pac_donor=direct_america_pac,
                    direct_save_america_pac_donor=direct_save_america,
                    
                    # PAC donations
                    affiliated_pac_conservative_total_donations=pac_conservative_total,
                    affiliated_pac_liberal_total_donations=pac_liberal_total,
                    affiliated_pac_total_donations=pac_total,
                    affiliated_pac_america_pac_donor=pac_america_pac,
                    affiliated_pac_save_america_pac_donor=pac_save_america,
                    
                    # senior_employee donations - only setting Trump donor for now
                    senior_employee_conservative_total_donations=senior_employee_conservative_total,
                    senior_employee_liberal_total_donations=senior_employee_liberal_total,
                    senior_employee_total_donations=senior_employee_total,
                    senior_employee_trump_donor=senior_employee_trump_donor,
                    senior_employee_america_pac_donor=senior_employee_america_pac,
                    senior_employee_save_america_pac_donor=senior_employee_save_america,
                )

                # Create the data source records
                for source_url in form_data['data_sources']:
                    if source_url:
                        DataSource.objects.get_or_create(
                            business=business,
                            url=source_url,
                            defaults={
                                'reason': 'import',
                                'is_approved': True
                            }
                        )

                # Update rate limit
                CSVImportRateLimit.objects.update_or_create(
                    user=request.user,
                    defaults={'last_import_attempt': timezone.now()}
                )

                messages.success(request, 'Business imported successfully!')
                return redirect('business_detail', slug=business.slug)

        except Exception as e:
            messages.error(request, f'Error importing business: {str(e)}')
            return render(request, 'companies/import_business.html', {
                'services': ServiceCategory.objects.all(),
                'products': ProductCategory.objects.all(),
                'form_data': form_data
            })

    return render(request, 'companies/import_business.html', {
        'services': ServiceCategory.objects.all(),
        'products': ProductCategory.objects.all(),
    })

def is_reviewer(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)

@permission_required('companies.can_review_edits', raise_exception=True)
def review_edit_request(request, edit_request_id):
    edit_request = get_object_or_404(
        EditRequest.objects.select_related('business', 'submitted_by'),  # Changed this line
        id=edit_request_id
    )

    if request.method == 'POST':
        action = request.POST.get('action')
        if action in ['approve', 'reject']:
            with transaction.atomic():
                edit_request.status = 'approved' if action == 'approve' else 'rejected'
                edit_request.reviewed_by = request.user
                edit_request.reviewed_at = timezone.now()
                edit_request.review_notes = request.POST.get('review_notes', '')
                edit_request.save()
                
                if action == 'approve':
                    # Apply the changes to the business
                    business = edit_request.business
                    
                    # Update basic info
                    if edit_request.name:
                        business.name = edit_request.name
                    if edit_request.description:
                        business.description = edit_request.description
                    
                    # Update service/product flags
                    if edit_request.provides_services is not None:
                        business.provides_services = edit_request.provides_services
                    if edit_request.provides_products is not None:
                        business.provides_products = edit_request.provides_products
                    
                    business.save()
                    
                    # Update political data
                    political_data = business.politicaldata
                    for field in ['conservative_percentage', 'conservative_total_donations',
                                'liberal_percentage', 'liberal_total_donations',
                                'trump_donor', 'america_pac_donor', 'save_america_pac_donor',
                                'data_source']:
                        value = getattr(edit_request, field)
                        if value is not None:
                            setattr(political_data, field, value)
                    political_data.save()

                    # approve the data source
                    edit_request.data_sources.all().update(is_approved=True)
                    
                    # Update services
                    if edit_request.services_to_add.exists():
                        business.services.add(*edit_request.services_to_add.all())
                    if edit_request.services_to_remove.exists():
                        business.services.remove(*edit_request.services_to_remove.all())
                    
                    # Update products
                    if edit_request.products_to_add.exists():
                        business.products.add(*edit_request.products_to_add.all())
                    if edit_request.products_to_remove.exists():
                        business.products.remove(*edit_request.products_to_remove.all())
                
                messages.success(request, f'Edit request {action}d successfully.')
                return redirect('review_edit_requests')
        pass

    # Prepare changes display
    changes = {}
    business = edit_request.business
    political_data = getattr(business, 'politicaldata', None)

    if edit_request.name:
        changes['Name'] = {
            'current': business.name,
            'proposed': edit_request.name
        }

    if edit_request.description:
        changes['Description'] = {
            'current': business.description,
            'proposed': edit_request.description
        }

    # Check political data changes
    political_fields = [
        ('conservative_percentage', 'Conservative Percentage'),
        ('conservative_total_donations', 'Conservative Total Donations'),
        ('liberal_percentage', 'Liberal Percentage'),
        ('liberal_total_donations', 'Liberal Total Donations'),
    ]

    if edit_request.description:
        changes['Description'] = {
            'current': business.description,
            'proposed': edit_request.description
        }

    # Check political data changes
    political_fields = [
        ('conservative_percentage', 'Conservative Percentage'),
        ('conservative_total_donations', 'Conservative Total Donations'),
        ('liberal_percentage', 'Liberal Percentage'),
        ('liberal_total_donations', 'Liberal Total Donations'),
    ]

    for field, label in political_fields:
        new_value = getattr(edit_request, field)
        if new_value is not None:
            current_value = getattr(political_data, field) if political_data else None
            changes[label] = {
                'current': f"{current_value:.2f}" if current_value is not None else "Not set",
                'proposed': f"{new_value:.2f}"
            }

    # Check boolean political fields
    boolean_fields = [
        ('trump_donor', 'Trump Donor'),
        ('america_pac_donor', 'America PAC Donor'),
        ('save_america_pac_donor', 'Save America PAC Donor'),
    ]

    for field, label in boolean_fields:
        new_value = getattr(edit_request, field)
        if new_value is not None:
            current_value = getattr(political_data, field) if political_data else False
            changes[label] = {
                'current': 'Yes' if current_value else 'No',
                'proposed': 'Yes' if new_value else 'No'
            }

    # Check data source changes
    if edit_request.data_source:
        changes['Data Source'] = {
            'current': political_data.data_source if political_data else '',
            'proposed': edit_request.data_source
        }

    # Check service changes
    if edit_request.services_to_add.exists():
        services_to_add = edit_request.services_to_add.all()
        changes['Services to Add'] = {
            'current': 'None',
            'proposed': ', '.join(s.name for s in services_to_add)
        }

    if edit_request.services_to_remove.exists():
        services_to_remove = edit_request.services_to_remove.all()
        changes['Services to Remove'] = {
            'current': ', '.join(s.name for s in services_to_remove),
            'proposed': 'Will be removed'
        }

    # Check product changes
    if edit_request.products_to_add.exists():
        products_to_add = edit_request.products_to_add.all()
        changes['Products to Add'] = {
            'current': 'None',
            'proposed': ', '.join(p.name for p in products_to_add)
        }

    if edit_request.products_to_remove.exists():
        products_to_remove = edit_request.products_to_remove.all()
        changes['Products to Remove'] = {
            'current': ', '.join(p.name for p in products_to_remove),
            'proposed': 'Will be removed'
        }

    # Check service/product provision changes
    if edit_request.provides_services is not None:
        changes['Provides Services'] = {
            'current': 'Yes' if business.provides_services else 'No',
            'proposed': 'Yes' if edit_request.provides_services else 'No'
        }

    if edit_request.provides_products is not None:
        changes['Provides Products'] = {
            'current': 'Yes' if business.provides_products else 'No',
            'proposed': 'Yes' if edit_request.provides_products else 'No'
        }
    
    return render(request, 'companies/review_edit_request.html', {
        'edit_request': edit_request,
        'changes': changes,
    })

@permission_required('companies.can_review_edits', raise_exception=True)
def review_edit_requests(request):
    # Get filters
    status = request.GET.get('status', 'pending')
    business_filter = request.GET.get('business', '')
    
    # Build queryset
    edit_requests = EditRequest.objects.select_related('business', 'submitted_by').order_by('-created_at')
    
    if status:
        edit_requests = edit_requests.filter(status=status)
    if business_filter:
        edit_requests = edit_requests.filter(business__name__icontains=business_filter)
    
    return render(request, 'companies/review_edit_requests.html', {
        'edit_requests': edit_requests,
        'status': status,
        'business_filter': business_filter,
    })

@login_required
def submit_update(request, business_id):
    business = get_object_or_404(Business.objects.prefetch_related('services', 'products'), id=business_id)
    
    def safe_float(value, default=0.0):
        """Convert string to float, returning default if empty or invalid"""
        try:
            return float(value) if value else default
        except ValueError:
            return default

    if request.method == 'POST':
        try:
            with transaction.atomic():
                edit_request = EditRequest.objects.create(
                    business=business,
                    submitted_by=request.user,
                    name=request.POST.get('name', ''),
                    description=request.POST.get('description', ''),
                    provides_services='provides_services' in request.POST,
                    provides_products='provides_products' in request.POST,

                    # Direct donations
                    direct_conservative_total_donations=safe_float(request.POST.get('direct_conservative_total_donations')),
                    direct_liberal_total_donations=safe_float(request.POST.get('direct_liberal_total_donations')),
                    direct_total_donations=safe_float(request.POST.get('direct_total_donations')),
                    direct_america_pac_donor=request.POST.get('direct_america_pac_donor') == 'on',
                    direct_save_america_pac_donor=request.POST.get('direct_save_america_pac_donor') == 'on',
                    
                    # PAC donations
                    affiliated_pac_conservative_total_donations=safe_float(request.POST.get('affiliated_pac_conservative_total_donations')),
                    affiliated_pac_liberal_total_donations=safe_float(request.POST.get('affiliated_pac_liberal_total_donations')),
                    affiliated_pac_total_donations=safe_float(request.POST.get('affiliated_pac_total_donations')),
                    affiliated_pac_america_pac_donor=request.POST.get('affiliated_pac_america_pac_donor') == 'on',
                    affiliated_pac_save_america_pac_donor=request.POST.get('affiliated_pac_save_america_pac_donor') == 'on',
                    
                    # Senior employee donations
                    senior_employee_conservative_total_donations=safe_float(request.POST.get('senior_employee_conservative_total_donations')),
                    senior_employee_liberal_total_donations=safe_float(request.POST.get('senior_employee_liberal_total_donations')),
                    senior_employee_total_donations=safe_float(request.POST.get('senior_employee_total_donations')),
                    senior_employee_trump_donor=request.POST.get('senior_employee_trump_donor') == 'on',
                    senior_employee_america_pac_donor=request.POST.get('senior_employee_america_pac_donor') == 'on',
                    senior_employee_save_america_pac_donor=request.POST.get('senior_employee_save_america_pac_donor') == 'on',
                    
                    justification=request.POST['justification'],
                    supporting_links=request.POST.get('supporting_links', '')
                )

                # Handle new data sources
                data_sources = request.POST.getlist('new_data_sources[]')
                for source_url in data_sources:
                    if source_url:
                        DataSource.objects.get_or_create(
                            business=business,
                            url=source_url,
                            defaults={
                                'reason': 'update',
                                'is_approved': False,
                                'edit_request': edit_request
                            }
                        )

                # Handle services/products changes
                if 'services_to_add' in request.POST:
                    edit_request.services_to_add.set(request.POST.getlist('services_to_add'))
                if 'services_to_remove' in request.POST:
                    edit_request.services_to_remove.set(request.POST.getlist('services_to_remove'))
                if 'products_to_add' in request.POST:
                    edit_request.products_to_add.set(request.POST.getlist('products_to_add'))
                if 'products_to_remove' in request.POST:
                    edit_request.products_to_remove.set(request.POST.getlist('products_to_remove'))
                
                messages.success(request, 'Update request submitted successfully! It will be reviewed by our team.')
                return redirect('business_search')
                
        except Exception as e:
            messages.error(request, f'Error submitting update: {str(e)}')
            return render(request, 'companies/submit_update.html', {
                'error': str(e),
                'business': business,
                'form_data': request.POST,
                'available_services': ServiceCategory.objects.all(),
                'available_products': ProductCategory.objects.all(),
            })
    
    # For GET request, show form with current values
    political_data = getattr(business, 'politicaldata', None)
    initial_data = {
        'name': business.name,
        'description': business.description,
        'provides_services': business.provides_services,
        'provides_products': business.provides_products,
    }
    
    return render(request, 'companies/submit_update.html', {
        'business': business,
        'form_data': initial_data,
        'political_data': political_data,
        'available_services': ServiceCategory.objects.all(),
        'available_products': ProductCategory.objects.all(),
        'current_data_sources': business.data_sources.all().order_by('-created_at')
    })
