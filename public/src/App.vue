<script setup></script>

<template>
  <router-view v-if="$route" />
  <div v-else class="container">UBD Public</div>
</template>
