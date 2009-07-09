<?xml version='1.0' encoding='UTF-8'?>
<!-- Transforms Solr query results to XML that Internet Archive expects -->
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="xml"/>

  <xsl:template match="/">
    <results status="ok">
      <xsl:text>&#10;</xsl:text>
      <xsl:apply-templates select="//response/lst"/>
      <hits mode="default">
        <xsl:text>&#10;</xsl:text>
        <xsl:apply-templates select="response/result/doc"/>
      </hits>
      <xsl:text>&#10;</xsl:text>
    </results>
  </xsl:template>

  
  <xsl:template match="doc">
    <hit number="{//response//result/@start + position() - 1}">
      <xsl:attribute name="score">
        <xsl:value-of select="float[@name='score']"/>
      </xsl:attribute>
      <xsl:text>&#10;</xsl:text>
      <metadata>
        <xsl:apply-templates select="*"/>
      </metadata>
      <xsl:text>&#10;</xsl:text>
    </hit>
    <xsl:text>&#10;</xsl:text>
  </xsl:template>


  <xsl:template match="str|long|date|int|float">
    <xsl:if test="boolean(@name)  and  not(@name = 'score')">
      <xsl:element name="{@name}">
        <xsl:value-of select="text()"/>
      </xsl:element>
    </xsl:if>
    <xsl:if test="not(boolean(@name))">
      <xsl:element name="{parent::node()/@name}">
        <xsl:value-of select="text()"/>
      </xsl:element>
    </xsl:if>
    <xsl:text>&#10;</xsl:text>
  </xsl:template>

  
  <xsl:template match="//response/lst">
    <xsl:variable name="params" select="lst[@name='params']"/>
    <xsl:variable name="q"      select="$params/str[@name='q']"/>
    <xsl:variable name="num"    select="count(//response/result/doc)"/>
    <xsl:variable name="start"  select="//response/result/@start"/>
    <info>
      <xsl:text>&#10;</xsl:text>
      <type_of_request>query</type_of_request>
      <xsl:text>&#10;</xsl:text>
      <query>
        <xsl:if test="boolean($params/str[@name='qin'])">
          <xsl:value-of select="$params/str[@name='qin']"/>
        </xsl:if>
        <xsl:if test="not(boolean($params/str[@name='qin']))">
          <xsl:value-of select="$q"/>
        </xsl:if>
      </query>
      <xsl:text>&#10;</xsl:text>
      <expanded_query>
        <xsl:value-of select="$q"/>
      </expanded_query>
      <xsl:text>&#10;</xsl:text>
      <sorted_by>
        <xsl:if test="contains($q,';')"><xsl:value-of
          select="normalize-space(substring-after($q, ';'))"/>
        </xsl:if>
        <xsl:if test="not(contains($q,';'))">relevance</xsl:if>
      </sorted_by>
      <xsl:text>&#10;</xsl:text>
      <range_info>
        <xsl:text>&#10;</xsl:text>
        <total_nbr>
          <xsl:value-of select="//response/result/@numFound"/>
        </total_nbr>
        <xsl:text>&#10;</xsl:text>
        <begin>
          <xsl:value-of select="$start"/>
        </begin>
        <xsl:text>&#10;</xsl:text>
        <end>
          <xsl:value-of select="$start + $num - 1"/>
        </end>
        <xsl:text>&#10;</xsl:text>
        <contained_in_this_set>
          <xsl:value-of select="$num"/>
        </contained_in_this_set>
        <xsl:text>&#10;</xsl:text>
      </range_info>
      <xsl:text>&#10;</xsl:text>
      <time_duration unit="milliseconds">
        <xsl:text>&#10;</xsl:text>
        <total>
          <xsl:value-of select="int[@name='QTime']"/>
        </total>
        <xsl:text>&#10;</xsl:text>
      </time_duration>
      <xsl:text>&#10;</xsl:text>
    </info>
    <xsl:text>&#10;</xsl:text>
  </xsl:template>

  
</xsl:stylesheet>
