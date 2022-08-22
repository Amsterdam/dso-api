REST Framework Intro
====================

As this project is deeply based on Django REST Framework,
it's good to give a quick overview beyond the standard "serializer" flow that everyone is familiar with.

An overview of relevant components (yellow are our custom classes, blue are base classes):

.. graphviz::

   digraph foo {
      node [shape=record color="grey60" style=filled fillcolor="#A5DFDF"]
      edge [color="grey30"]

      # Needs "cluster_" prefix to work!
      subgraph cluster_routers {
        label="Routers"
        labeljust="l"
        color=blue

        BaseRouter [fillcolor="#9AD0F5"]

        BaseRouter -> SimpleRouter [dir=back arrowtail=empty]
        SimpleRouter -> DefaultRouter [dir=back arrowtail=empty]
        DefaultRouter -> DynamicRouter [dir=back arrowtail=empty]

        DynamicRouter [fillcolor="#FFE6AA"]
      }

      subgraph cluster_views {
        label="Views"
        labeljust="l"
        color=blue

        View [fillcolor="#9AD0F5"]
        View -> APIView
        APIView -> GenericAPIView [dir=back arrowtail=empty]
      }

      subgraph cluster_viewsets {
        label="Viewsets"
        labeljust="l"
        color=blue

        ViewSetMixin [fillcolor="#9AD0F5"]

        APIView -> ViewSet [dir=back arrowtail=empty weight=20 minlen=6]
        BaseRouter -> ViewSetMixin [style=dotted]
        ViewSetMixin -> ViewSet [dir=back arrowtail=empty]
        ViewSetMixin -> GenericViewSet [dir=back arrowtail=empty]
        GenericAPIView -> GenericViewSet [dir=back arrowtail=empty weight=20 minlen=6]
        GenericViewSet -> ReadOnlyModelViewSet [dir=back arrowtail=empty]
        GenericViewSet -> ModelViewSet [dir=back arrowtail=empty]

        DSOViewMixin -> DynamicApiViewSet [dir=back arrowtail=empty]
        DSOViewMixin -> RemoteViewSet [dir=back arrowtail=empty]
        ViewSet -> RemoteViewSet [dir=back arrowtail=empty]
        ReadOnlyModelViewSet -> DynamicApiViewSet [dir=back arrowtail=empty]

        DynamicApiViewSet [fillcolor="#FFE6AA"]
        DSOViewMixin [fillcolor="#FFE6AA"]
        RemoteViewSet [fillcolor="#FFE6AA"]
      }

      subgraph cluster_request {
        label="Request"
        labeljust="l"
        color=blue

        APIView -> Request [style=dotted minlen=2 weight=2]

        HttpRequest -> WSGIRequest [dir=back arrowtail=empty]
        WSGIRequest -> Request [dir=back arrowtail=empty]
     }

      subgraph cluster_renderers {
        label="Renderers"
        labeljust="l"
        color=blue

        BaseRenderer [fillcolor="#9AD0F5"]

        BaseRenderer -> CSVRenderer [dir=back arrowtail=empty]
        BaseRenderer -> JSONRenderer [dir=back arrowtail=empty]
        JSONRenderer -> GeoJSONRenderer [dir=back arrowtail=empty]
        JSONRenderer -> HALJSONRenderer [dir=back arrowtail=empty]

        GeoJSONRenderer [fillcolor="#FFE6AA"]
        HALJSONRenderer [fillcolor="#FFE6AA"]
      }

      subgraph cluster_response {
        label="Response"
        labeljust="l"
        color=blue

        HttpResponseBase [fillcolor="#9AD0F5"]

        HttpResponseBase -> HttpResponse [dir=back arrowtail=empty]
        HttpResponseBase -> StreamingHttpResponse [dir=back arrowtail=empty]
        HttpResponse -> SimpleTemplateResponse [dir=back arrowtail=empty]
        SimpleTemplateResponse -> Response [dir=back arrowtail=empty]
        StreamingHttpResponse -> StreamingResponse [dir=back arrowtail=empty]

        Response -> BaseRenderer [style=dotted label="accepted_renderer"]
        StreamingResponse -> BaseRenderer [style=dotted]

        StreamingResponse [fillcolor="#FFE6AA"]
      }

      subgraph cluster_parsers {
        label="Parsers"
        labeljust="l"
        color=blue

        BaseParser [fillcolor="#9AD0F5"]

        BaseParser -> JSONParser [dir=back arrowtail=empty]
        JSONParser -> DSOJSONParser [dir=back arrowtail=empty]

        DSOJSONParser [fillcolor="#FFE6AA"]
      }

      subgraph cluster_filters {
        label="Filters"
        labeljust="l"
        color=blue

        BaseFilterBackend [fillcolor="#9AD0F5"]

        BaseFilterBackend -> OrderingFilter [dir=back arrowtail=empty]
        OrderingFilter -> DSOOrderingFilter [dir=back arrowtail=empty]

        DSOOrderingFilter [fillcolor="#FFE6AA"]
      }

      subgraph cluster_serializers {
        label="Serializers"
        labeljust="l"
        color=blue

        Field [fillcolor="#9AD0F5"]
        BaseSerializer [fillcolor="#9AD0F5"]

        Field -> BaseSerializer [dir=back arrowtail=empty]
        BaseSerializer -> ListSerializer [dir=back arrowtail=empty]
        Field -> CharField [dir=back arrowtail=empty]
        Field -> RelatedField [dir=back arrowtail=empty]
        Field -> GeometryField [dir=back arrowtail=empty]

        ListSerializer -> Serializer [label="child"]

        RelatedField -> HyperlinkedRelatedField [dir=back arrowtail=empty]
        HyperlinkedRelatedField -> TemporalHyperlinkedRelatedField [dir=back arrowtail=empty]
        GeometryField -> DSOGeometryField [dir=back arrowtail=empty]

        BaseSerializer -> Serializer [dir=back arrowtail=empty]
        Serializer -> DSOSerializer [dir=back arrowtail=empty]
        Serializer -> ModelSerializer [dir=back arrowtail=empty]
        ModelSerializer -> DSOModelSerializer [dir=back arrowtail=empty]
        DSOSerializer -> DSOModelSerializer [dir=back arrowtail=empty]

        TemporalHyperlinkedRelatedField [fillcolor="#FFE6AA"]
        DSOSerializer [fillcolor="#FFE6AA"]
        DSOModelSerializer [fillcolor="#FFE6AA"]
        DSOGeometryField [fillcolor="#FFE6AA"]
      }

      GenericAPIView -> BaseFilterBackend [label="filter_backends" style=dotted minlen=3]
      GenericAPIView -> BasePagination [label="pagination_class" style=dotted minlen=3]
      GenericAPIView -> ModelSerializer [label="serializer_class" style=dotted]


      APIView -> BaseAuthentication [label="authentication_classes" style=dotted minlen=3]
      APIView -> BaseParser [label="parser_classes" style=dotted minlen=3]
      APIView -> BaseRenderer [label="renderer_classes" style=dotted]
      APIView -> BasePermission [label="permission_classes" style=dotted minlen=2]
      # APIView -> BaseContentNegotiation [label="content_negotiation_class"]
      # APIView -> BaseMetadata [label="metadata_class"]
      # APIView -> BaseVersioning [label="versioning_class"]
      # APIView -> BaseThrottle [label="throttle_classes"]

      subgraph cluster_authentication {
        label="Authentication"
        labeljust="l"
        color=blue

        BaseAuthentication [fillcolor="#9AD0F5"]
        BaseAuthentication -> BasicAuthentication
        BaseAuthentication -> TokenAuthentication
      }

      subgraph cluster_pagination {
        label="Pagination"
        labeljust="l"
        color=blue

        BasePagination [fillcolor="#9AD0F5"]

        BasePagination -> PageNumberPagination [dir=back arrowtail=empty]
        PageNumberPagination -> DSOHTTPHeaderPageNumberPagination [dir=back arrowtail=empty]
        DSOHTTPHeaderPageNumberPagination -> DelegatedPageNumberPagination [dir=back arrowtail=empty]
        DelegatedPageNumberPagination -> DSOPageNumberPagination [dir=back arrowtail=empty]

        DSOHTTPHeaderPageNumberPagination [fillcolor="#FFE6AA"]
        DelegatedPageNumberPagination [fillcolor="#FFE6AA"]
        DSOPageNumberPagination [fillcolor="#FFE6AA"]
      }

      subgraph cluster_permissions {
        label="Permissions"
        labeljust="l"
        color=blue

        BasePermission [fillcolor="#9AD0F5"]

        BasePermission -> HasOAuth2Scopes
        HasOAuth2Scopes [fillcolor="#FFE6AA"]
      }
   }


Views
-----

To understand Django REST Framework, it's good to understand
it's base view classes have the following "pipeline":

.. graphviz::

   digraph foo {
        rankdir=LR
        node [shape=cds]
        edge [style=invis minlen=1]

        paginate [label="paginate (queryset)"]
        paginate2 [label="paginate (result)"]

        parse -> authenticate -> collect -> filter -> paginate -> serialize -> paginate2 -> render

        subgraph cluster_generic {
            label="Part of GenericAPIView";
            color=darkgray
            style=dotted

            collect
            filter
            paginate
            serialize
            paginate2
        }
   }

This is both the strength and weakness of Django REST Framework.
Each step has swappable components and can be extended.
However, the paginator doesn't really take the rendering format into account,
nor does the filtering know what attributes are rendered by the serializer.
These weaknesses are handled by deeply inspecting the source code for possible hooks,
and moving along with the natural flow that REST framework has.

The "parse" step happens in ``APIView.initial()``, which has pluggable components for:

* Request parsing (for POST/PUT/PATCH)
* Response formats / content negotiation
* Version handling (bare)
* Authentication
* Permission checks
* Throttling

The ``GenericAPIView`` adds the following standard functionality to the view:

* Serializer initialization
* Filtering via pluggable backends
* Pagination

Ofcourse, one can also subclass ``APIView`` and do this manually.

Serializers
-----------

Where a view binds all request handling, the "serializer" defines what the layout of the input/output
should look like. The serializer uses a composite design pattern for this.

Each item in the JSON dictionary is generated by a serializer :class:`~rest_framework.serializers.Field`.
To generate special output, a new field subclass can be added with custom ``to_represention()`` logic.

Serializer objects are also subclasses from :class:`~rest_framework.serializers.Field`.
This allows to create nested object structures.
The serializer field just happens to generate a dictionary
instead of a single scalar in ``to_represention()``.

An array or listing happens by adding ``many=True`` to the serializer initialization.
This little shortcut actually triggers behavior in ``Serializer.__new__()``
to wrap the whole serializer into a ``ListSerializer`` object.
The list serializer is also just a field. It just happens to generate a list in ``to_represention()``.

In the end, this whole "tree of field objects" walks through the data structure.
Each field has a ``source`` (parsed into ``source_attrs``) that tells what model field
it should read. The whole structure cascades through relations and nestings by blindly reading
attributes that ``get_attribute()`` and ``to_representation()`` happen to do for each field subclass.

Viewsets
--------

The "Viewset" logic builds on top of this to handle both the "listing" and "detail" view
in the same viewset class.
This project only offers a GET API, so it uses the :class:`~rest_framework.viewsets.ReadOnlyModelViewSet`.
They also offer a like a full GET/POST/PUT/DELETE API using :class:`~rest_framework.viewsets.ModelViewSet`.


Routers
-------

The "router" is a special component that handles automatic URL creation,
e.g. to create a separate listing and detail URL from a single "viewset".
This project overrides the router to implement the whole creation of all URLs.
