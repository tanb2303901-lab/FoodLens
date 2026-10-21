"""Offline OpenAPI/example checks. Development dependencies only; no credentials."""
from decimal import Decimal
import json
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from openapi_spec_validator import validate


def assert_schema(spec, schema, value):
    # Decimal avoids binary floating-point errors for grams multipleOf=0.001.
    root = json.loads(json.dumps({'components': spec['components'], **schema}), parse_float=Decimal)
    data = json.loads(json.dumps(value), parse_float=Decimal)
    Draft202012Validator(root, format_checker=FormatChecker()).validate(data)


def validate_examples(spec, document):
    validate(spec)
    seen = set()
    for case in document['examples']:
        if case['id'] in seen:
            raise ValueError('Duplicate example ID')
        seen.add(case['id'])
        operation = spec['paths'][case['path']][case['method'].lower()]
        request, response = case['request'], case['response']
        groups = {'path': request.get('path_params', {}), 'query': request.get('query', {}),
                  'header': {k.lower(): v for k, v in request.get('headers', {}).items()}}
        for parameter in operation.get('parameters', []):
            name = parameter['name'].lower() if parameter['in'] == 'header' else parameter['name']
            values = groups[parameter['in']]
            if parameter.get('required') and name not in values:
                # Negative examples deliberately omit a required header.
                if parameter['in'] != 'header' or response['status'] not in (422, 428):
                    raise ValueError('Missing example parameter: ' + parameter['name'])
            if name in values:
                assert_schema(spec, parameter['schema'], values[name])
        if 'body' in request:
            schema = operation['requestBody']['content']['application/json']['schema']
            if case.get('invalid_request'):
                try:
                    assert_schema(spec, schema, request['body'])
                except ValidationError:
                    pass
                else:
                    raise ValueError('Negative example unexpectedly satisfies input schema')
            else:
                assert_schema(spec, schema, request['body'])
        if 'multipart' in request:
            assert_schema(spec, operation['requestBody']['content']['multipart/form-data']['schema'], request['multipart'])
        result = operation['responses'][str(response['status'])]
        if response['status'] == 204:
            if 'body' in response:
                raise ValueError('204 must have no response body')
        else:
            assert_schema(spec, result['content']['application/json']['schema'], response['body'])
        headers = {k.lower(): v for k, v in response['headers'].items()}
        for name, header in result.get('headers', {}).items():
            if name.lower() in headers:
                value = headers[name.lower()]
                if header['schema'].get('type') == 'boolean':
                    if value not in ('true', 'false'):
                        raise ValueError('Invalid boolean response header')
                    value = value == 'true'
                assert_schema(spec, header['schema'], value)
        if headers.get('cache-control') != 'no-store' or 'x-request-id' not in headers:
            raise ValueError('Missing request/cache response headers')
        body = response.get('body', {})
        if 'error' in body and body['error']['request_id'] != headers['x-request-id']:
            raise ValueError('Request ID mismatch')
    return len(seen)
