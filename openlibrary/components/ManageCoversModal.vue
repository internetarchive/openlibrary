<template>
    <div class="coversNew">
        <button type="button" @click="showModal = !showModal">Manage Covers</button>
        <div @click="showModal = false" class="modal" :class="{hidden: !showModal}" :key="showModal">
            <div class="modal-content-wrapper">
                <div @click.stop="" class="modal-content">
                    <span class="close" @click="showModal = !showModal">&times;</span>
                    <h1 class="center">Covers</h1>
                    <a @click="showAdd = true" :class="{bold: showAdd}" href="javascript:;">Add</a> |
                    <a @click="showAdd = false" :class="{bold: !showAdd}" href="javascript:;">Manage</a>
                    <hr>

                    <div class="resp-container" :class="{hidden: !showAdd}">
                        <iframe class="resp-iframe" :src="addCoversUrl"></iframe>
                    </div>
                    <div class="resp-container" :class="{hidden: showAdd}">
                        <iframe class="resp-iframe" :src="manageCoversUrl"></iframe>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script>
export default {
    props: {
        identifier: {
            type: String,
            default: () => 'default' // example: /works/OL45310W
        },
    },
    data: () => {
        return {
            showModal: false,
            showAdd: true,
        }
    },
    computed: {
        addCoversUrl: function () {
            return `${location.origin}${this.identifier}/a/add-cover`
        },
        manageCoversUrl: function () {
            return `${location.origin}${this.identifier}/a/manage-covers`
        },
    },
    mounted() {
        window.addEventListener('message', this.receiveMessage)
    },
    methods: {
        receiveMessage(event) {
            if (event.data.message === 'closeCoverModal') this.showModal = false;
        }
    },
}
</script>
<style>

.resp-container {
    position: relative;
    overflow: hidden;
    padding-top: 56.25%;
    height: 100%;
}

.resp-iframe {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    border: 0;
}

.coversNew {
    display: flex;
    justify-content: center;
}

.hidden {
    display: none !important;
}

.modal {
    display: block; /* Hidden by default */
    position: fixed; /* Stay in place */
    z-index: 2; /* Sit on top */
    left: 0;
    top: 0;
    width: 100%; /* Full width */
    height: 100%; /* Full height */
    /*overflow-y: hidden; !* Enable scroll if needed *!*/
    background-color: rgb(0, 0, 0); /* Fallback color */
    background-color: rgba(0, 0, 0, 0.4); /* Black w/ opacity */
}

@media screen and (max-width: 768px) {
    .modal-content-wrapper {
        margin-top: 75px;
    }
}

.modal-content-wrapper {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
}

.modal-content {
    background-color: #fefefe;
    padding: 20px;
    border: 1px solid #888;
    width: 640px; /* set to this number to match the old covers modal */
    height: 100%;
}

/* The Close Button */
.close {
    color: #aaa;
    float: right;
    font-size: 28px;
    font-weight: bold;
}

.close:hover,
.close:focus {
    color: black;
    text-decoration: none;
    cursor: pointer;
}

.bold {
    font-weight: bold;
}

.center {
    text-align: center;
}
</style>
